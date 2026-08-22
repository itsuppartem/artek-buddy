# 2. Team vs Private desktop

## Status

Accepted.

## Context

A Pi 5 may run the host stack plus more than one Chromium box. Giving every
bot its own container is isolation; sharing one box is RAM.

## Decision

**Team** (default) is one container `artek-bot-team-{workspace}` and one home
`data/homes/team-{workspace}`. Team bots take turns; a waiter sees the holder’s
name. **Private** is `artek-bot-{bot_id}` and `data/homes/{bot_id}` and can run
beside Team.

Chat, memory, and routines are already per-bot. The switch only chooses the
box. Changing mode rebinds the bot; it does not copy the old home.

Create spec (CapDrop, memory/CPU/pids) is the same for both. Limits are sized
for Team plus one Private on an 8 GiB Pi 5.

## Consequences

Two Private bots plus Team can still OOM the Pi; that is an operator choice.
Team Reset wipes the shared home for every Team bot. Idle Stop is Sleeping,
not Offline.
