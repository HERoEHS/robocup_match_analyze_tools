#include <csignal>
#include <cstdlib>
#include <functional>
#include <iostream>

static std::function<void()> g_cleanup_fn;

static void signal_handler(int sig) {
  (void)sig;
  if (g_cleanup_fn) {
    g_cleanup_fn();
  }
  std::signal(sig, SIG_DFL);
  std::raise(sig);
}

void install_watchdog(std::function<void()> cleanup) {
  g_cleanup_fn = cleanup;
  std::signal(SIGINT, signal_handler);
  std::signal(SIGTERM, signal_handler);
  std::signal(SIGSEGV, signal_handler);
}
