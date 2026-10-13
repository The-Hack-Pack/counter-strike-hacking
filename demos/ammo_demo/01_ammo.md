# Ammo
## Debugging
```
pgrep -af xash3d
gdb -q -p GAME_PID
```

## Searching memory
```bash
source /home/mahaloz/cs_game_build/counter-strike-hacking/lab/tools/gdb_ammo.py
ammo-scan 20
```

```
ammo-list 0
ammo-save /tmp/ammo-search.json
```

## Viewing memory
Observing the change in memoery:
```bash
p gHUD.m_Ammo.m_pWeapon->szName
p/d gHUD.m_Ammo.m_pWeapon->iClip

# vars
set $clip = &gHUD.m_Ammo.m_pWeapon->iClip
p/x $clip
x/wd $clip

# break 
watch -l *$clip
continue

# change the val
set var *$clip = 9
```

## Binary
`0x553A2`
