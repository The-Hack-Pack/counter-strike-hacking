#!/usr/bin/env python3
"""Add the Hack Pack hooks to an isolated pinned CS16Client source tree."""
from pathlib import Path
import argparse, shutil
p=argparse.ArgumentParser();p.add_argument('source',type=Path);a=p.parse_args()
root=Path(__file__).resolve().parents[1]
changes={
 'cl_dll/hud.h': [('class CHudAmmo: public CHudBase\n{', 'class CHudAmmo: public CHudBase\n{\npublic:\n\tWEAPON *HP_Weapon() const { return m_pWeapon; }\nprivate:')],
 'cl_dll/cdll_int.cpp': [('\tPM_Move( ppmove, server );','\tPM_Move( ppmove, server );\n\tHP_PlayerMove(ppmove);'),('\tgHUD.Init();','\tgHUD.Init();\n\tHP_Init();'),('\tgHUD.Redraw( time, intermission );','\tgHUD.Redraw( time, intermission );\n\tHP_Draw();'),('void DLLEXPORT HUD_Frame( double time )\n{','void DLLEXPORT HUD_Frame( double time )\n{\n\tHP_Frame();')],
 'cl_dll/entity.cpp': [('void DLLEXPORT HUD_TxferLocalOverrides( struct entity_state_s *state, const struct clientdata_s *client )\n{','void DLLEXPORT HUD_TxferLocalOverrides( struct entity_state_s *state, const struct clientdata_s *client )\n{\n\tHP_ClientData(client);')],
 'cl_dll/StudioModelRenderer.cpp': [('void CStudioModelRenderer::StudioSaveBones(void)\n{','void CStudioModelRenderer::StudioSaveBones(void)\n{\n\tHP_Bones(m_pCurrentEntity, m_pStudioHeader, *m_pbonetransform);')],
}
for rel,replacements in changes.items():
 f=a.source/rel;s=f.read_text()
 if '#include "hackpack_lab.h"' in s:continue
 for before,after in replacements:
  if s.count(before)!=1:raise RuntimeError(f'{rel}: expected one hook anchor, got {s.count(before)}')
  s=s.replace(before,after,1)
 f.write_text('#include "hackpack_lab.h"\n'+s)
f=a.source/'cl_dll/input.cpp';s=f.read_text()
if '#include "hackpack_lab.h"' not in s:
 start=s.index('void DLLEXPORT CL_CreateMove');open_brace=s.index('{',start);depth=1;end=open_brace+1
 while depth:
  if s[end]=='{':depth+=1
  elif s[end]=='}':depth-=1
  end+=1
 s=s[:end-1]+'\n\tHP_Move(cmd, active);\n'+s[end-1:]
 f.write_text('#include "hackpack_lab.h"\n'+s)
for name in ['hackpack_lab.h','hackpack_lab.cpp']:
 shutil.copy2(root/'client'/name,a.source/'cl_dll'/name)
print('Applied classroom hooks to',a.source)
