// Hack Pack teaching overlay. All modifications default to off.
// The UDP bridge binds loopback only; Xash owns the actual game connection.
#include "hud.h"
#include "cl_util.h"
#include "hackpack_lab.h"
#include "draw_util.h"
#include "usercmd.h"
#include "pm_defs.h"
#include "pmtrace.h"
#include "const.h"
#include "cl_entity.h"
#include "entity_state.h"
#include "triangleapi.h"
#include "event_api.h"
#include "studio.h"
#include "screenfade.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <sstream>
#include <string>
#include <sys/socket.h>
#include <sys/prctl.h>
#include <sys/random.h>
#include <arpa/inet.h>
#include <fcntl.h>
#include <unistd.h>

static cvar_t *esp, *radar, *aim, *autofire, *bhop, *speed, *external,
              *bridgePort, *autojoin, *autobuy, *aimFov, *fireInterval, *labHud;
static double WallTime() {
    return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
}
static float speedApplied = 1;
static int bridge = -1, boundPort = 0;
static double lastFrame = 0, lastBuy = 0, lastJoin = 0, lastFire = 0;
static double aliveSince = 0;
static bool wasAlive = false;
static int targetSlot = 0;
static clientdata_t serverData = {};
static Vector predictedOrigin, velocity, punch;
static int onground = -1;
struct Observation {
    int message = -1;
    double received = 0, boneTime = 0;
    Vector position, head, boneOrigin;
    bool hitbox = false;
};
static Observation seen[MAX_PLAYERS + 1];
struct Action {
    unsigned long sequence = 0;
    double received = 0;
    float pitch = 0, yaw = 0, forward = 0, side = 0;
    unsigned int buttons = 0;
};
static Action action;

static float Clamp(float v, float low, float high) { return std::max(low, std::min(high, v)); }
static float Wrap(float angle) {
    while (angle > 180) angle -= 360;
    while (angle < -180) angle += 360;
    return angle;
}
static void Toggle(cvar_t *c) { gEngfuncs.Cvar_SetValue(c->name, c->value ? 0 : 1); }
static void ToggleESP() { Toggle(esp); }
static void ToggleRadar() { Toggle(radar); }
static void ToggleAim() { Toggle(aim); }
static void ToggleBhop() { Toggle(bhop); }
static void CycleSpeed() { gEngfuncs.Cvar_SetValue("hp_speed", speed->value < 1.5f ? 2 : speed->value < 2.5f ? 3 : 1); }
static void Off() {
    for (cvar_t *c : {esp, radar, aim, autofire, bhop, external}) gEngfuncs.Cvar_SetValue(c->name, 0);
    gEngfuncs.Cvar_SetValue("hp_speed", 1);
    gEngfuncs.Cvar_SetValue("sys_timescale", 1);
    speedApplied = 1; action = {}; targetSlot = 0;
}
static void Status() {
    cl_entity_t *local = gEngfuncs.GetLocalPlayer();
    WEAPON *weapon = gHUD.m_Ammo.HP_Weapon();
    cvar_t *clock = gEngfuncs.pfnGetCvarPointer("sys_timescale");
    gEngfuncs.Con_Printf("HP_STATUS slot=%d team=%d hp=%d clip=%d weapon=%d speed=%.3f target=%d\n",
        local ? local->index : 0, g_iTeamNumber, gHUD.m_Health.m_iHealth,
        weapon ? weapon->iClip : -1, weapon ? weapon->iId : 0, clock ? clock->value : 1, targetSlot);
    gEngfuncs.Con_Printf("HP_MEMORY clip_address=%p sys_timescale_value=%p (addresses vary with ASLR)\n",
        weapon ? (void *)&weapon->iClip : nullptr, clock ? (void *)&clock->value : nullptr);
}
void HP_Init() {
    esp = CVAR_CREATE("hp_esp", "0", 0);
    radar = CVAR_CREATE("hp_radar", "0", 0);
    aim = CVAR_CREATE("hp_aim", "0", 0);
    autofire = CVAR_CREATE("hp_autofire", "0", 0);
    bhop = CVAR_CREATE("hp_bhop", "0", 0);
    speed = CVAR_CREATE("hp_speed", "1", 0);
    external = CVAR_CREATE("hp_external", "0", 0);
    bridgePort = CVAR_CREATE("hp_bridge_port", "0", 0);
    autojoin = CVAR_CREATE("hp_autojoin", "0", 0);
    autobuy = CVAR_CREATE("hp_autobuy", "0", 0);
    aimFov = CVAR_CREATE("hp_aim_fov", "35", 0);
    fireInterval = CVAR_CREATE("hp_fire_interval", "0.25", 0);
    labHud = CVAR_CREATE("hp_hud", "0", 0);
    gEngfuncs.pfnAddCommand("hp_toggle_esp", ToggleESP);
    gEngfuncs.pfnAddCommand("hp_toggle_radar", ToggleRadar);
    gEngfuncs.pfnAddCommand("hp_toggle_aim", ToggleAim);
    gEngfuncs.pfnAddCommand("hp_toggle_bhop", ToggleBhop);
    gEngfuncs.pfnAddCommand("hp_speed_cycle", CycleSpeed);
    gEngfuncs.pfnAddCommand("hp_off", Off);
    gEngfuncs.pfnAddCommand("hp_status", Status);
    // Upstream seeds qport from whole seconds. Machines behind the same NAT
    // can otherwise collide when students start together. Keep the wire format
    // and cookie checks, but choose the 16-bit connection identifier independently.
    cvar_t *qport=gEngfuncs.pfnGetCvarPointer("net_qport");
    unsigned int nonce=0;
    if(qport && getrandom(&nonce,sizeof(nonce),GRND_NONBLOCK)==sizeof(nonce)) {
        int flags=qport->flags;qport->flags &= ~(1<<17); // engine FCVAR_READ_ONLY
        gEngfuncs.Cvar_SetValue("net_qport",1+(nonce%65535));qport->flags=flags;
    }
    // Explicit launch-time opt-in permits same-user debuggers without changing Yama globally.
    if (getenv("HACKPACK_ALLOW_PTRACE")) prctl(PR_SET_PTRACER, PR_SET_PTRACER_ANY, 0, 0, 0);
    gEngfuncs.Con_Printf("Hack Pack lab loaded. hp_off resets the source overlay.\n");
}
void HP_PlayerMove(playermove_s *move) {
    predictedOrigin = move->origin; velocity = move->velocity;
    punch = move->punchangle; onground = move->onground;
}
void HP_ClientData(const clientdata_s *data) { serverData = *data; }
void HP_Bones(cl_entity_s *entity, void *studioHeader, float bones[][3][4]) {
    studiohdr_t *header = static_cast<studiohdr_t *>(studioHeader);
    if (!entity || !entity->player || entity->index < 1 || entity->index > MAX_PLAYERS) return;
    mstudiobbox_t *boxes = (mstudiobbox_t *)((byte *)header + header->hitboxindex);
    for (int i = 0; i < header->numhitboxes; ++i) {
        if (boxes[i].group != 1 || boxes[i].bone < 0 || boxes[i].bone >= header->numbones) continue;
        Vector center = (Vector(boxes[i].bbmin) + Vector(boxes[i].bbmax)) * 0.5f;
        Observation &o = seen[entity->index];
        for (int j = 0; j < 3; ++j)
            o.head[j] = bones[boxes[i].bone][j][3] + center[0]*bones[boxes[i].bone][j][0]
                + center[1]*bones[boxes[i].bone][j][1] + center[2]*bones[boxes[i].bone][j][2];
        o.boneOrigin = entity->origin; o.boneTime = WallTime(); o.hitbox = true;
        return;
    }
}
static Vector Eye() {
    Vector origin = predictedOrigin;
    float height[3] = {0, 0, 17};
    gEngfuncs.pEventAPI->EV_LocalPlayerViewheight(height);
    return origin + Vector(height);
}
static void Observe() {
    const double now = WallTime();
    for (int i = 1; i <= MAX_PLAYERS; ++i) {
        hud_player_info_t info = {}; gEngfuncs.pfnGetPlayerInfo(i, &info);
        cl_entity_t *e = gEngfuncs.GetEntityByIndex(i);
        if (!info.name || !*info.name || !e || !e->model || !e->player) {
            seen[i] = {}; seen[i].message = -1; continue;
        }
        if (e->curstate.messagenum != seen[i].message) {
            seen[i].message = e->curstate.messagenum;
            seen[i].received = now; seen[i].position = e->curstate.origin;
        }
    }
}
static Vector Head(int slot) {
    const Observation &o = seen[slot];
    if (o.hitbox && WallTime() - o.boneTime < 0.5)
        return o.head + (o.position - o.boneOrigin);
    cl_entity_t *e = gEngfuncs.GetEntityByIndex(slot);
    return o.position + Vector(0, 0, e && e->curstate.usehull ? 12 : 28);
}
static bool Visible(const Vector &point) {
    Vector start = Eye(), finish = point;
    pmtrace_t *tr = gEngfuncs.PM_TraceLine(start, finish, PM_STUDIO_IGNORE, 2, -1);
    return tr && tr->fraction > 0.999f;
}
static bool Enemy(int i, int localSlot) {
    int team = g_PlayerExtraInfo[i].teamnumber;
    return i != localSlot && (team == 1 || team == 2) && team != g_iTeamNumber
        && !g_PlayerExtraInfo[i].dead && seen[i].received > 0 && WallTime() - seen[i].received < 0.35;
}
static std::string Quote(const char *s) {
    std::string out = "\"";
    if (s) for (; *s; ++s) {
        unsigned char c = *s;
        if (c == '"' || c == '\\') out += '\\';
        if (c >= 32) out += (char)c;
    }
    return out + "\"";
}
static void Vec(std::ostream &out, const Vector &v) { out << '[' << v[0] << ',' << v[1] << ',' << v[2] << ']'; }
static std::string Snapshot() {
    std::ostringstream out; out.setf(std::ios::fixed); out.precision(3);
    cl_entity_t *local = gEngfuncs.GetLocalPlayer();
    int slot = local ? local->index : 0;
    WEAPON *weapon = gHUD.m_Ammo.HP_Weapon();
    cvar_t *clock = gEngfuncs.pfnGetCvarPointer("sys_timescale");
    float angles[3] = {}; gEngfuncs.GetViewAngles(angles);
    out << "{\"version\":1,\"wall_time\":" << WallTime() << ",\"map\":" << Quote(gEngfuncs.pfnGetLevelName())
        << ",\"target\":" << targetSlot << ",\"local\":{\"slot\":" << slot << ",\"team\":" << g_iTeamNumber
        << ",\"alive\":" << ((g_iTeamNumber == 1 || g_iTeamNumber == 2) && gHUD.m_Health.m_iHealth > 0 && slot>0 && !g_PlayerExtraInfo[slot].dead ? "true" : "false")
        << ",\"health\":" << gHUD.m_Health.m_iHealth << ",\"clip_hud\":" << (weapon ? weapon->iClip : -1)
        << ",\"weapon\":" << (weapon ? weapon->iId : 0) << ",\"speed\":" << (clock ? clock->value : 1)
        << ",\"ground\":" << (onground != -1 ? "true" : "false") << ",\"origin\":"; Vec(out, predictedOrigin);
    out << ",\"server_origin\":"; Vec(out, serverData.origin);
    out << ",\"eye\":"; Vec(out, Eye()); out << ",\"velocity\":"; Vec(out, velocity);
    out << ",\"punch\":"; Vec(out, punch); out << ",\"view\":"; Vec(out, Vector(angles));
    out << "},\"players\":["; bool first = true;
    for (int i = 1; i <= MAX_PLAYERS; ++i) {
        hud_player_info_t info = {}; gEngfuncs.pfnGetPlayerInfo(i, &info);
        if (!info.name || !*info.name || !seen[i].received) continue;
        if (!first) out << ','; first = false;
        double age = std::max(0.0, WallTime() - seen[i].received);
        Vector head = Head(i);
        out << "{\"slot\":" << i << ",\"name\":" << Quote(info.name) << ",\"team\":" << g_PlayerExtraInfo[i].teamnumber
            << ",\"dead\":" << (g_PlayerExtraInfo[i].dead ? "true" : "false") << ",\"age\":" << age
            << ",\"fresh\":" << (age < 0.35 ? "true" : "false") << ",\"visible\":" << (Visible(head) ? "true" : "false")
            << ",\"head_source\":" << Quote(seen[i].hitbox && WallTime()-seen[i].boneTime < 0.5 ? "hitbox" : "estimate")
            << ",\"origin\":"; Vec(out, seen[i].position); out << ",\"head\":"; Vec(out, head); out << '}';
    }
    out << "],\"probes\":[";
    for (int i=0; i<8; ++i) {
        float a = (angles[1]+i*45)*0.01745329252f;
        Vector start=predictedOrigin, end=start+Vector(cosf(a)*128,sinf(a)*128,0.0f);
        pmtrace_t *tr = gEngfuncs.PM_TraceLine(start,end,PM_STUDIO_IGNORE,0,-1);
        if(i)out<<','; out << (tr ? tr->fraction : 0);
    }
    out << "]}"; return out.str();
}
static void Bridge() {
    int port = (int)bridgePort->value;
    if (port != boundPort) {
        if (bridge >= 0) close(bridge); bridge = -1; boundPort = port; action = {};
        if (port >= 1024 && port < 65535) {
            bridge = socket(AF_INET, SOCK_DGRAM, 0);
            sockaddr_in address = {}; address.sin_family = AF_INET; address.sin_addr.s_addr = htonl(INADDR_LOOPBACK); address.sin_port = htons(port);
            if (bridge < 0 || bind(bridge, (sockaddr *)&address, sizeof(address))) {
                if(bridge>=0)close(bridge); bridge=-1; gEngfuncs.Con_Printf("HP bridge bind failed on %d\n",port);
            } else fcntl(bridge, F_SETFL, O_NONBLOCK);
        }
    }
    if (bridge < 0) return;
    char packet[2048]; ssize_t length;
    while ((length = recv(bridge, packet, sizeof(packet)-1, 0)) > 0) {
        packet[length]=0;
        Action next;
        if (sscanf(packet,"HP1 %lu %f %f %f %f %u",&next.sequence,&next.pitch,&next.yaw,&next.forward,&next.side,&next.buttons)==6
            && next.sequence > action.sequence && std::isfinite(next.pitch) && std::isfinite(next.yaw)
            && std::isfinite(next.forward) && std::isfinite(next.side)) {
            next.received=WallTime(); next.pitch=Clamp(next.pitch,-89,89); next.yaw=Wrap(next.yaw);
            next.forward=Clamp(next.forward,-400,400); next.side=Clamp(next.side,-400,400);
            next.buttons &= IN_ATTACK|IN_JUMP|IN_DUCK|IN_RELOAD; action=next;
        } else if (!strncmp(packet,"CMD1 ",5)) {
            // Local lecture/testing control. It has no route into the server console.
            gEngfuncs.pfnClientCmd(packet+5);
        }
    }
}
void HP_Frame() {
    if (!esp) return;
    Bridge();
    if (speed->value != speedApplied) {
        speedApplied = Clamp(speed->value,1,4); gEngfuncs.Cvar_SetValue("sys_timescale",speedApplied);
    }
    const char *level=gEngfuncs.pfnGetLevelName();
    if(!level || !*level)return;
    Observe();
    const double now=WallTime();
    if (autojoin->value && gEngfuncs.GetLocalPlayer() && now-lastJoin>2 && g_iTeamNumber!=1 && g_iTeamNumber!=2) {
        lastJoin=now;
        gEngfuncs.pfnServerCmd(autojoin->value==2 ? "jointeam 2\n" : "jointeam 1\n");
        gEngfuncs.pfnServerCmd("joinclass 1\n");
    }
    cl_entity_t *self=gEngfuncs.GetLocalPlayer();
    bool alive=(g_iTeamNumber==1 || g_iTeamNumber==2) && gHUD.m_Health.m_iHealth>0 && self && self->index>0 && !g_PlayerExtraInfo[self->index].dead;
    if(autojoin->value && alive && !wasAlive && g_pMenu)g_pMenu->HideVGUIMenu();
    if(alive && !wasAlive)aliveSince=now;
    WEAPON *current=gHUD.m_Ammo.HP_Weapon();
    bool hasPrimary=current && current->iSlot==0;
    if (autobuy->value && alive && !hasPrimary && now-aliveSince<5 && now-lastBuy>0.5) {
        lastBuy=now;
        gEngfuncs.pfnServerCmd(g_iTeamNumber==1 ? "ak47\n" : "m4a1\n");
        for(int i=0;i<3;++i)gEngfuncs.pfnServerCmd("primammo\n");
        gEngfuncs.pfnServerCmd("deagle\n");gEngfuncs.pfnServerCmd("secammo\n");gEngfuncs.pfnServerCmd("vesthelm\n");
    }
    wasAlive=alive;
    if (now-lastFrame<0.1) return;
    lastFrame=now; std::string snapshot=Snapshot();
    if (const char *path=getenv("HACKPACK_STATE_PATH")) {
        std::string temp=std::string(path)+".tmp";
        FILE *f=fopen(temp.c_str(),"w"); if(f){fwrite(snapshot.data(),1,snapshot.size(),f);fputc('\n',f);fclose(f);rename(temp.c_str(),path);}
    }
    if(bridge>=0) {
        sockaddr_in peer={};peer.sin_family=AF_INET;peer.sin_addr.s_addr=htonl(INADDR_LOOPBACK);peer.sin_port=htons(boundPort+1);
        sendto(bridge,snapshot.data(),snapshot.size(),0,(sockaddr *)&peer,sizeof(peer));
    }
}
void HP_Move(usercmd_s *cmd, int active) {
    if (!esp || !active) return;
    if(external->value) {
        if(WallTime()-action.received<0.25) {
            cmd->viewangles=Vector(action.pitch,action.yaw,0.0f);cmd->forwardmove=action.forward;cmd->sidemove=action.side;cmd->buttons=action.buttons;
            gEngfuncs.SetViewAngles(cmd->viewangles);
        } else {cmd->buttons=0;cmd->forwardmove=cmd->sidemove=cmd->upmove=0;}
    }
    if(bhop->value && (cmd->buttons&IN_JUMP) && onground==-1) cmd->buttons &= ~IN_JUMP;
    targetSlot=0;
    if(!aim->value || gHUD.m_Health.m_iHealth<=0 || (!autofire->value && !(cmd->buttons&IN_ATTACK)))return;
    Observe();cl_entity_t *local=gEngfuncs.GetLocalPlayer(); if(!local)return;
    float best=Clamp(aimFov->value,1,180); Vector bestAngles;
    for(int i=1;i<=MAX_PLAYERS;++i) {
        if(!Enemy(i,local->index))continue;
        Vector head=Head(i);if(!Visible(head))continue;
        Vector delta=head-Eye();float horizontal=sqrtf(delta[0]*delta[0]+delta[1]*delta[1]);
        Vector angles(-atan2f(delta[2],horizontal)*57.2957795f,atan2f(delta[1],delta[0])*57.2957795f,0.0f);
        float error=hypotf(Wrap(angles[0]-cmd->viewangles[0]),Wrap(angles[1]-cmd->viewangles[1]));
        if(error<best){best=error;targetSlot=i;bestAngles=angles;}
    }
    if(!targetSlot)return;
    cmd->viewangles=Vector(Clamp(bestAngles[0]-punch[0],-89,89),Wrap(bestAngles[1]-punch[1]),0.0f);
    // Stop strafing while shooting to avoid movement spread. No server bullet logic is changed.
    cmd->forwardmove=cmd->sidemove=0; gEngfuncs.SetViewAngles(cmd->viewangles);
    if(autofire->value) {
        cmd->buttons &= ~IN_ATTACK;
        if(WallTime()-lastFire>=Clamp(fireInterval->value,0.1f,2)){cmd->buttons|=IN_ATTACK;lastFire=WallTime();}
    }
}
static bool Project(const Vector &p,int &x,int &y) {
    Vector point=p,screen;
    if(gEngfuncs.pTriAPI->WorldToScreen(point,screen))return false;
    x=(int)((screen[0]+1)*ScreenWidth*0.5f);y=(int)((1-screen[1])*ScreenHeight*0.5f);
    return x>=0&&x<ScreenWidth&&y>=0&&y<ScreenHeight;
}
void HP_Draw() {
    if(!esp)return;
    const char *level=gEngfuncs.pfnGetLevelName();if(!level || !*level)return;
    cl_entity_t *local=gEngfuncs.GetLocalPlayer(); if(!local)return;
    if(labHud->value) {
        char label[160];cvar_t *clock=gEngfuncs.pfnGetCvarPointer("sys_timescale");
        snprintf(label,sizeof(label),"Hack Pack  speed %.1fx | ESP %.0f radar %.0f aim %.0f bhop %.0f | F10: off",
            clock?clock->value:1,esp->value,radar->value,aim->value,bhop->value);
        DrawUtils::DrawHudString(20,ScreenHeight-95,ScreenWidth-20,label,255,220,120);
    }
    const int size=200,left=ScreenWidth-size-20,top=40;
    bool fullmap=strstr(gEngfuncs.pfnGetLevelName(),"de_dust2")!=nullptr;
    auto RadarPoint=[&](const Vector &position,int &x,int &y) {
        if(fullmap){x=left+(int)Clamp((position[0]+2400)/4400*size,4,size-4);y=top+size-(int)Clamp((position[1]+1200)/4600*size,4,size-4);}
        else {Vector d=position-predictedOrigin;x=left+size/2+(int)Clamp(d[0]/20,-96,96);y=top+size/2-(int)Clamp(d[1]/20,-96,96);}
    };
    if(radar->value){FillRGBA(left,top,size,size,10,15,25,210);FillRGBA(left+size/2,top,1,size,80,90,105,160);FillRGBA(left,top+size/2,size,1,80,90,105,160);
        DrawUtils::DrawHudString(left,top-18,ScreenWidth,fullmap?"DUST2: bright=fresh, dim=cached":"RADAR: bright=fresh, dim=cached",230,230,230);}
    for(int i=1;i<=MAX_PLAYERS;++i) {
        if(i==local->index || !seen[i].received || g_PlayerExtraInfo[i].dead)continue;
        double age=WallTime()-seen[i].received;if(age>10)continue;
        bool enemy=g_PlayerExtraInfo[i].teamnumber!=g_iTeamNumber;
        int r=enemy?255:80,g=enemy?90:170,b=enemy?80:255,alpha=age<0.35?255:80;
        if(radar->value){int x,y;RadarPoint(seen[i].position,x,y);
            FillRGBA(x-3,y-3,7,7,r,g,b,alpha);char text[32];snprintf(text,sizeof(text),"%d",i);DrawUtils::DrawHudString(x+5,y-5,ScreenWidth,text,r,g,b);}
        if(esp->value && age<0.35){int x,y,fx,fy;Vector head=Head(i);
            if(Project(head,x,y)&&Project(seen[i].position-Vector(0,0,34),fx,fy)){
                int h=std::max(12,fy-y+8),w=std::max(8,h/3);
                FillRGBA(x-w/2,y-4,w,2,r,g,b,255);FillRGBA(x-w/2,y+h-4,w,2,r,g,b,255);
                FillRGBA(x-w/2,y-4,2,h,r,g,b,255);FillRGBA(x+w/2-2,y-4,2,h,r,g,b,255);
                char text[64];snprintf(text,sizeof(text),"slot %d %s",i,Visible(head)?"clear":"behind wall");
                DrawUtils::DrawHudString(x-w/2,y-23,ScreenWidth,text,r,g,b);
            }}
    }
    if(radar->value){int x,y;RadarPoint(predictedOrigin,x,y);FillRGBA(x-3,y-3,7,7,255,255,255,255);}
}
