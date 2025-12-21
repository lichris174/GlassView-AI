# GlassView-AI
Screen assistant tool built around a Tauri v2 framework, running qwen3-vl locally to provide descriptive answers with proper reasoning.

Commit 1 (12/7/2025):

Working backend and UI, screenshot tool is fully functional and can be combined with a prompt

Since the model runs locally, internet access is currently not functional, but will (maybe) be added later on

Responses may time out at times when prompt is too complex, planning on potentially migrating to another local AI, or potentially getting rid of the VLM for an LLM

Note that the translucent blurred UI may only work on certain systems, try tweaking hardware acceleration settings and disabling battery saver 



Commit 2 (12/21/2025):

Sidebar implemented, and model is now switched to the instruct version of qwen3-vl with 8B parameters. Responses should come a lot quicker

App stores past chats locally, all of which can be quickly recalled, enabling for breaking up workflows into longer sessions

Screenshot tool is a bit buggy, Ctrl + alt + shift + m SHOULD open it up regardless of whether the app is minimized/maximized, but there seems to be some inconsistencies


