#pragma once
struct usercmd_s;
struct playermove_s;
struct clientdata_s;
struct cl_entity_s;
void HP_Init();
void HP_Frame();
void HP_Draw();
void HP_Move(usercmd_s *cmd, int active);
void HP_PlayerMove(playermove_s *move);
void HP_ClientData(const clientdata_s *data);
void HP_Bones(cl_entity_s *entity, void *studioHeader, float bones[][3][4]);
