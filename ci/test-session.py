#!/usr/bin/env python3
"""用硬件调用替身执行会话控制原始代码，验证默认行为和调试开关。"""
import argparse
from pathlib import Path
import subprocess

PREFIX = r'''
#include <cstdint>
#include <cstddef>
#include <cstdarg>
#include <cstdio>
#include <cassert>
#include <array>
#include <map>
#include <string>
#include <vector>
struct Stop {};
using clock_sec_t = uint64_t;
using clock_usec_t = uint32_t;
using thread_t = int;
using wait_result_t = int;
using kern_return_t = int;
constexpr int THREAD_NULL = 0, KERN_SUCCESS = 0;
enum {kPEPanicBegin=1, kPEPanicRestartCPU, kPEPanicRestartCPUNoCallouts, kPEHaltCPU, kPERestartCPU};
static int (*PE_halt_restart)(unsigned int);
static std::map<std::string,uint32_t> args;
static std::vector<std::array<uint64_t,3>> calls;
static uint64_t milliseconds;
static unsigned pmic_calls;
static bool worker_started;
static bool PE_parse_boot_argn(const char *key, void *out, size_t) {
 auto p=args.find(key); if(p==args.end()) return false; *(uint32_t*)out=p->second; return true;
}
static void IOLog(const char *, ...) {}
static void IOSleep(unsigned n) { milliseconds+=n; if(milliseconds>=35000) throw Stop{}; }
static void clock_get_system_microtime(clock_sec_t *s, clock_usec_t *u) {*s=milliseconds/1000; *u=0;}
static int kernel_thread_start(void (*)(void*,wait_result_t), void*, thread_t *out) {
 worker_started=true; *out=1; return 0;
}
static void thread_deallocate(thread_t) {}
extern "C" int liuqin_pmic_poweroff(void) {pmic_calls++; return -1;}
'''
MOCK = '''static LiuqinSmcResult liuqin_smc(uint64_t fn, uint64_t a1 = 0, uint64_t a2 = 0)
{
    calls.push_back({fn, a1, a2});
    return {0, 0, 0, 0};
}

'''
TESTS = r'''
int main(int argc, char **argv) {
 assert(argc==2); std::string test=argv[1];
 if(test=="panic") args["liuqin_panic_reset"]=1;
 if(test=="halt") args["liuqin_halt_reset"]=1;
 if(test=="uptime") args["liuqin_uptime"]=2;
 if(test=="watchdog" || test=="panic-no-pet") {args["liuqin_wdt_bite"]=32; args["liuqin_wdt_pet"]=10;}
 if(test=="invalid") {args["liuqin_wdt_bite"]=180; args["liuqin_wdt_pet"]=10;}
 if(test=="disable") {args["liuqin_wdt_bite"]=0; args["liuqin_wdt_pet"]=10;}
 pong_halt_install(); assert(PE_halt_restart==pong_halt_restart);
 if(test=="default") {
  assert(calls.empty() && !worker_started); pong_halt_restart(kPEHaltCPU);
  assert(pmic_calls==1 && calls.back()[0]==0x84000008u); calls.clear();
  pong_halt_restart(kPEPanicBegin); pong_halt_restart(kPEPanicRestartCPU); assert(calls.empty());
 } else if(test=="panic") {
  pong_halt_restart(kPEPanicBegin); assert(calls.empty()); pong_halt_restart(kPEPanicRestartCPU);
  assert(calls.size()==1 && calls[0][0]==0x84000009u);
 } else if(test=="halt") {
  pong_halt_restart(kPEHaltCPU); assert(pmic_calls==0 && calls.size()==1 && calls[0][0]==0x84000009u);
 } else if(test=="uptime") {
  assert(worker_started); try {liuqin_session_worker(nullptr,0);} catch(Stop&) {}
  assert(calls.size()==1 && calls[0][0]==0x84000009u && milliseconds>=8000);
 } else if(test=="watchdog" || test=="panic-no-pet") {
  assert(worker_started && calls.size()==3);
  assert((calls[0]==std::array<uint64_t,3>{0x86000005u,2,0}));
  assert((calls[1]==std::array<uint64_t,3>{0x86000008u,32000,32000}));
  assert((calls[2]==std::array<uint64_t,3>{0x86000005u,3,0}));
  if(test=="panic-no-pet") pong_halt_restart(kPEPanicBegin);
  try {liuqin_session_worker(nullptr,0);} catch(Stop&) {}
  assert(calls.size()==(test=="panic-no-pet" ? 3u : 6u));
 } else if(test=="invalid") {
  assert(calls.empty() && !worker_started && liuqin_wdt_pet==0);
 } else if(test=="disable") {
  assert(calls.size()==1 && calls[0][0]==0x86000005u && calls[0][1]==2 && !worker_started);
 } else assert(false);
 std::printf("PASS %s\n",argv[1]);
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    header = (Path(__file__).resolve().parent / 'overrides/LiuqinSession.h').read_text(encoding='utf-8')
    start = header.index('static LiuqinSmcResult liuqin_smc(')
    end = header.index('static void liuqin_reset(void)', start)
    text = header[:start] + MOCK + header[end:]
    text = text.replace('#include <kern/thread.h>', '')
    text = text.replace('__attribute__((weak_import))', '__attribute__((weak))')
    text = text.replace('__asm__ volatile("dsb sy" ::: "memory");', '')
    text = text.replace('__asm__ volatile("wfi");', 'throw Stop{};')
    args.output.mkdir(parents=True, exist_ok=False)
    source = args.output / 'session-test.cpp'
    source.write_text(PREFIX + text + TESTS, encoding='utf-8')
    binary = args.output / 'session-test'
    subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(binary)], check=True)
    for name in ('default', 'panic', 'halt', 'uptime', 'watchdog', 'panic-no-pet', 'invalid', 'disable'):
        subprocess.run([str(binary), name], check=True)


if __name__ == '__main__':
    main()
