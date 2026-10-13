# Autonomous-Robot
This is a final year electronics engineering project this is a larger version of path following robot, where the bot uses computer vision to autonomously determine its own path, we also have a display too demonstrate facial expressions and for user interface.

## Opening the Qt interface from the animated face

Build the CMake project in `ui` with Qt Creator. The generated executable must
be named `ui` (or `ui.exe`) and placed under `ui/build`; this is Qt Creator's
usual build location. Then run the face animation:

```powershell
python src/main.py
```

While the face-animation window has keyboard focus, press `I` to open the Qt
interface. Pressing `I` again does not create another interface window.

If your Qt build output is stored elsewhere, set `ROBOT_UI_EXECUTABLE` to its
full path before launching the animation:

```powershell
$env:ROBOT_UI_EXECUTABLE = "C:\path\to\ui.exe"
python src/main.py
```
