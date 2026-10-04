# DLL API validation — 0.13

2026-10-04: Linux x64 Release build; 12/12 CTest tests passed.
Header, Windows .def and Linux shared-library exports contain the same 19 C API names.
No Windows DLL was built or executed for this update.
Previous supplied-DLL inspection: [history](history/PRE_CHANNEL_DLL_VALIDATION.md).

Channel tests: all 8 algorithms, channel-8 noise, measured output timing, pre-pan independence, summed channel output vs mix (float rounding tolerance), existing render equality, split rendering, clone, reset, invalid arguments, state replay including channel filters.
See tests/test_channels.cpp and CHANNEL_VALIDATION.txt.
