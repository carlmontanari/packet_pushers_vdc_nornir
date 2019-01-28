# packet_pushers_vdc_nornir

# Introduction

This is a follow up to my CI/CD for networking presentation for Packet Pushers VDC 3; this time, instead of using Ansible, I am using "pure Python" (Nornir, NAPALM, Netmiko) to render configurations, create backups, push configurations, and test/validate configurations.

You can find the original Ansible version of this demo [here](https://github.com/carlniger/packet_pushers_vdc).

You can read about Nornir at the following links:
[Nonir Docs](https://nornir.readthedocs.io/en/stable/)
[Kirk Byer's Intro to Nornir](https://pynet.twb-tech.com/blog/nornir/intro.html)
[Patrick Ogenstad's Intro to Nornir](https://networklore.com/introducing-brigade/)

# Caveats/Notes

Currently the EOS config replace fails on the rollback tasks. AFAIK this is due to there being no "exit" statements after entering neighbor configuration of the BGP section. I plan to write a quick helper function to clean that so its not an issue but haven't done so yet.

# Issues/Questions

Please feel free to open an issue if you've got any issues/questions. I will be messing around with this repo for a little while I suspect!