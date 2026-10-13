#!/usr/bin/env python3
"""Python decisions, native Xash transport: join, search a waypoint graph, aim and fire.

The bot never reads server-console state. Its observations come only from its own client.
"""
import argparse
import heapq
import json
import math
import os
from pathlib import Path
import random
import socket
import subprocess
import time

def distance(a,b):return math.dist(a,b)
def angles(eye,target,punch=(0,0,0)):
    dx,dy,dz=(target[i]-eye[i] for i in range(3))
    return max(-89,min(89,-math.degrees(math.atan2(dz,math.hypot(dx,dy)))-punch[0])), math.degrees(math.atan2(dy,dx))-punch[1]

class Navigation:
    def __init__(self,path):
        self.nodes=json.loads(Path(path).read_text())['nodes']
        self.goals=[n['id'] for n in self.nodes if n['flags']&(1<<4)] or list(range(0,len(self.nodes),100))
    def nearest(self,point):return min(range(len(self.nodes)),key=lambda i:distance(point,self.nodes[i]['origin']))
    def astar(self,start,goal):
        frontier=[(0,start)];cost={start:0};previous={}
        while frontier:
            _,current=heapq.heappop(frontier)
            if current==goal:
                path=[goal]
                while path[-1]!=start:path.append(previous[path[-1]])
                return path[::-1]
            for link in self.nodes[current]['links']:
                nxt=link['to'];step=distance(self.nodes[current]['origin'],self.nodes[nxt]['origin'])
                candidate=cost[current]+step
                if candidate<cost.get(nxt,float('inf')):
                    cost[nxt]=candidate;previous[nxt]=current
                    heapq.heappush(frontier,(candidate+distance(self.nodes[nxt]['origin'],self.nodes[goal]['origin']),nxt))
        return []

class Brain:
    def __init__(self,navigation,fire_interval=0.3,rng=None):
        self.nav=navigation;self.fire_interval=fire_interval;self.last_fire=0;self.last_plan=0;self.route=[];self.patrol=0
        self.mode='waiting';self.target=None;self.route_target=None;self.last_jump=0;self.goal=None
        self.rng=rng if rng is not None else random.Random()
        self.reset_stuck()

    def reset_stuck(self):
        self.stuck_waypoint=None;self.progress_distance=None;self.stuck_since=0
        self.recovery_until=0;self.recovery_side=0;self.next_recovery=0

    def recover(self,state,waypoint,probe,now,forward,side,buttons):
        local=state['local'];origin=local['origin'];point=self.nav.nodes[waypoint]['origin']
        remaining=math.hypot(origin[0]-point[0],origin[1]-point[1])
        # Height changes and wall jitter do not count as progress along the route.
        if waypoint!=self.stuck_waypoint:
            self.reset_stuck();self.stuck_waypoint=waypoint
            self.progress_distance=remaining;self.stuck_since=now
        elif self.progress_distance-remaining>8:
            self.progress_distance=remaining;self.stuck_since=now
        if now-self.stuck_since>1.2 and local['ground'] and now-self.last_jump>0.8 and now>=self.next_recovery:
            left=state['probes'][(probe+2)%8];right=state['probes'][(probe-2)%8]
            direction=self.rng.choice((-1,1)) if abs(left-right)<0.2 else (-1 if left>right else 1)
            self.recovery_side=direction*self.rng.uniform(180,280)
            self.recovery_until=now+self.rng.uniform(0.3,0.5)
            self.next_recovery=now+self.rng.uniform(0.9,1.4)
            buttons|=1<<1;self.last_jump=now
        if now<self.recovery_until:
            self.mode='unstick';forward=min(forward,180);side=self.recovery_side
        return forward,side,buttons

    def step(self,state,now=None):
        now=time.monotonic() if now is None else now;local=state['local'];origin=local['origin']
        pitch,yaw=local['view'][:2];forward=side=buttons=0;self.target=None
        if not local['alive'] or local['team'] not in (1,2):
            self.mode='waiting';self.route=[];self.route_target=None;self.goal=None;self.reset_stuck();return pitch,yaw,0,0,0
        enemies=[p for p in state['players'] if p['slot']!=local['slot'] and p['team'] in (1,2) and p['team']!=local['team'] and not p['dead'] and p['age']<10]
        visible=[p for p in enemies if p['fresh'] and p['visible']]
        if visible:
            target=min(visible,key=lambda p:distance(origin,p['origin']));self.target=target['slot'];self.mode='engage'
            self.reset_stuck()
            pitch,yaw=angles(local['eye'],target['head'],local['punch'])
            if local['clip_hud']==0:buttons=1<<13  # IN_RELOAD
            elif math.hypot(*local['velocity'][:2])<15 and now-self.last_fire>=self.fire_interval:
                buttons=1;self.last_fire=now
            return pitch,yaw,0,0,buttons
        if not self.route or (enemies and now-self.last_plan>2):
            self.last_plan=now;start=self.nav.nearest(origin)
            if enemies:
                target=min(enemies,key=lambda p:distance(origin,p['origin']));goal=self.nav.nearest(target['origin']);self.route_target=target['slot']
            else:
                goal=self.nav.goals[self.patrol%len(self.nav.goals)];self.patrol+=1;self.route_target=None
            self.goal=goal;route=self.nav.astar(start,goal);self.route=route[1:] if len(route)>1 else route
        self.target=self.route_target if any(p['slot']==self.route_target for p in enemies) else None
        self.mode='pursue' if self.target is not None else 'search'
        while self.route:
            point=self.nav.nodes[self.route[0]]['origin']
            if math.hypot(origin[0]-point[0],origin[1]-point[1])<40 and abs(origin[2]-point[2])<70:self.route.pop(0)
            else:break
        if self.route:
            node=self.nav.nodes[self.route[0]];goal=node['origin'];pitch=0;yaw=math.degrees(math.atan2(goal[1]-origin[1],goal[0]-origin[0]));forward=300
            relative=(yaw-local['view'][1])%360;probe=int(round(relative/45))%8
            if state['probes'][probe]<0.2:forward=100;side=-220 if state['probes'][(probe+2)%8]>=state['probes'][(probe-2)%8] else 220
            if node['flags']&(1<<2):buttons|=1<<2
            forward,side,buttons=self.recover(state,self.route[0],probe,now,forward,side,buttons)
            if goal[2]-origin[2]>16 and math.hypot(goal[0]-origin[0],goal[1]-origin[1])<90 and local['ground'] and now-self.last_jump>0.8:
                buttons|=1<<1;self.last_jump=now
        else:self.reset_stuck()
        return pitch,yaw,forward,side,buttons

def send_command(sock,port,command):sock.sendto(('CMD1 '+command+'\n').encode(),('127.0.0.1',port))

def main():
    base=Path(__file__).resolve().parent;p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime',type=Path,help='A separate Linux runtime with the lab overlay installed.')
    p.add_argument('--server',default='cs.mahaloz.re:27015');p.add_argument('--team',choices=['t','ct'],default='t')
    p.add_argument('--port',type=int,default=49300);p.add_argument('--attach',action='store_true')
    p.add_argument('--headless',action='store_true',help='Use Xvfb and software OpenGL; retains animated head hitboxes.')
    p.add_argument('--seconds',type=float,default=0);p.add_argument('--name',default='mahaloz-bot')
    p.add_argument('--visualize',action='store_true',help='Serve a live position, route, and target map in your browser.')
    p.add_argument('--visualize-port',type=int,help='Local HTTP port for --visualize (default: bridge port + 2).')
    p.add_argument('--graph',type=Path,default=base/'data/de_dust2-waypoints.json');p.add_argument('--record',type=Path,default=Path('hackpack-bot.jsonl'))
    a=p.parse_args()
    viewer_port=a.port+2 if a.visualize_port is None else a.visualize_port
    if not a.attach and not a.runtime:p.error('--runtime is required unless --attach is used')
    if not 1024<=a.port<=65533:p.error('Choose a bridge port between 1024 and 65533')
    if not a.name.strip() or any(ord(c)<32 or c in '\";\\' for c in a.name):p.error('--name must be nonempty and contain no control characters, quotes, semicolons, or backslashes')
    if a.visualize_port is not None and not a.visualize:p.error('--visualize-port requires --visualize')
    if a.visualize and not 1024<=viewer_port<=65535:p.error('Choose a visualization port between 1024 and 65535')
    if a.visualize and viewer_port in (a.port,a.port+1):p.error('Choose a visualization port different from the bridge ports')
    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',a.port+1));sock.settimeout(.5)
    child=xvfb=viewer=None;engine_log=None;brain=Brain(Navigation(a.graph));sequence=0;last_mode=None;started=time.monotonic()
    try:
        if a.visualize:
            from bot_viewer import BotViewer
            viewer=BotViewer(brain.nav.nodes,a.name,viewer_port,a.runtime)
            print(f'Live bot map: {viewer.url}',flush=True)
        if not a.attach:
            runtime=a.runtime.resolve();env=dict(os.environ,SDL_AUDIODRIVER='dummy')
            if a.headless:
                display=next((i for i in range(100,150) if not Path(f'/tmp/.X11-unix/X{i}').exists()),None)
                if display is None:raise RuntimeError('No free Xvfb display')
                xvfb=subprocess.Popen(['Xvfb',f':{display}','-screen','0','800x600x24','-ac'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                env.update(DISPLAY=f':{display}',LIBGL_ALWAYS_SOFTWARE='1');time.sleep(.3)
            engine_log=open(a.record.with_suffix('.engine.log'),'w')
            command=[str(runtime/'start.sh'),'-nosound','-log','-width','800','-height','600','+name',a.name,'+hp_bridge_port',str(a.port),'+hp_autojoin','1' if a.team=='t' else '2','+hp_autobuy','1','+fps_max','100']
            child=subprocess.Popen(command,cwd=runtime,env=env,stdout=engine_log,stderr=subprocess.STDOUT)
            # Startup menus execute after +commands; connect once the menu finishes initializing.
            time.sleep(2);send_command(sock,a.port,'connect '+a.server)
        send_command(sock,a.port,f'name "{a.name}"\nhp_off\nhp_external 1')
        with a.record.open('w') as record:
            while not a.seconds or time.monotonic()-started<a.seconds:
                if child and child.poll() is not None:raise RuntimeError(f'Native engine exited: {child.returncode}')
                try:data=sock.recv(65535)
                except socket.timeout:
                    if time.monotonic()-started>35 and not sequence:raise RuntimeError('No gameplay telemetry; inspect the engine log and connection address')
                    continue
                state=json.loads(data);expected_map=Path(state.get('map','')).stem
                if expected_map!='de_dust2':raise RuntimeError('This waypoint file is for de_dust2; provide a graph matching the server map')
                command=brain.step(state);sequence+=1
                sock.sendto(('HP1 %d %.4f %.4f %.2f %.2f %d'%((sequence,)+command)).encode(),('127.0.0.1',a.port))
                snapshot={'wall_time':time.monotonic(),'sequence':sequence,'name':a.name,'mode':brain.mode,'target':brain.target,'route':list(brain.route),'goal':brain.goal,'action':command,'state':state}
                record.write(json.dumps(snapshot)+'\n');record.flush()
                if viewer:viewer.update(snapshot)
                if brain.mode!=last_mode:
                    print(f'{brain.mode}: target={brain.target}, waypoints remaining={len(brain.route)}',flush=True);last_mode=brain.mode
    except KeyboardInterrupt:pass
    finally:
        try:send_command(sock,a.port,'hp_off')
        except OSError:pass
        if child:
            send_command(sock,a.port,'quit')
            try:child.wait(timeout=3)
            except subprocess.TimeoutExpired:child.kill();child.wait()
        if xvfb:xvfb.terminate();xvfb.wait(timeout=3)
        if viewer:viewer.close()
        if engine_log:engine_log.close()
        sock.close()

if __name__=='__main__':main()
