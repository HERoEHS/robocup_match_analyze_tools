#pragma once
#include <functional>

void install_watchdog(std::function<void()> cleanup = nullptr);
