# Counter Strike Hacking
Brought to you by The Hack Pack.

![](./screenshot.png) 

## Getting Started

We are playing Counter Strike 1.6. This is an oldver version of the famous Counter Strike: Global Offensive.
If you want to run the server yourself, follow the [server/README.md](server/README.md).

### Dowload The Client 
If you are student, download the modified client below to start. The password will be given in-person:
https://drive.proton.me/urls/M7E7QEVZ78#fmKicUj0FtAc

It is reccomend you use the Linux version if you plan to hack, else you can use any OS. This client is based on the reverse engineered client [cs16](https://github.com/Velaron/cs16-client). You can modify the source yourself to create your own hacked client. Using Codex or Claude Code to help is reccomended.

### Join The Server
You can find the live server at `cs.mahaloz.re`. To join, once you start the game, go to:
`Play CS -> Play Online -> Add IP`. 

Select `Xash3D 49` in the top bar, and add `cs.mahaloz.re`.


## Hacking
Instead of using the default client, you can use our modified hacked client.
Clone this repo down and do the following:
```bash
python3 install.py ../CS16Client-Linux-x86_64/ # path to the client folder
python3 launch.py ../CS16Client-Linux-x86_64 --server cs.mahaloz.re:27015 --name YourName --debug
```

This will start you up in the hacked client, and make it easier to debug your own client.
You can use any of the following keys to trigger hacked behavior.

| Key | Action |
|---|---|
| F5 | Toggle wall boxes |
| F6 | Toggle radar |
| F7 | Toggle head aiming while attack is held |
| F8 | Toggle repeated jumping while jump is held |
| F9 | Cycle simulation speed through 1×, 2×, 3× |
| F10 | Clear source features and restore speed to 1× |
| F11 | Print client state and memory addresses |


## Demos
You will find demo information and scripts inside of `./demos`. Each demo below demonstrates a different idea behind game hacking

### Demo1: Infinite Ammo (Client)
- Find ammo value in memory and modify it

### Demo2: Speed Hacks (BHop)
- The client enforces how fast you can click the space bar
- Also found in source [here](https://github.com/Velaron/cs16-client/blob/9778fec4c6f956d2b483949feb704fb479c92f7f/pm_shared/pm_shared.cpp#L2427)
- We can find it in the binary: 0xa9950
- We can modify it to allow us to always jump fast!
- Use `F8`

### Demo3: Walls & Radar
- Map resources are just a construct!
- Toggle with `F5`, `F6`, we can draw our own things

### Demo4: Aimbot
- Toggle with `F7`

### Demo5: Our own client! 
- Use the provided bot in the lab
```bash
python3 lab/bot.py --runtime .lab/bot --headless --visualize
```

## Modifying Your Client
- Open up Codex/Claude Code
- Request a feature in the `bot.py` or in your human client
