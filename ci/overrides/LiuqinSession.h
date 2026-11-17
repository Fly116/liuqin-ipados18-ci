#ifndef LIUQIN_SESSION_H
#define LIUQIN_SESSION_H

#include <kern/thread.h>

extern "C" int liuqin_pmic_poweroff(void) __attribute__((weak_import));
extern "C" void pong_log_panic_flush(void) __attribute__((weak_import));
static int (*pong_previous_halt_restart)(unsigned int);
static uint32_t pong_panic_latched;
static uint32_t liuqin_panic_reset, liuqin_halt_reset;
static uint32_t liuqin_uptime, liuqin_wdt_pet;

struct LiuqinSmcResult { uint64_t a0, a1, a2, a3; };

static LiuqinSmcResult liuqin_smc(uint64_t fn, uint64_t a1 = 0, uint64_t a2 = 0)
{
    register uint64_t x0 __asm__("x0") = fn;
    register uint64_t x1 __asm__("x1") = a1;
    register uint64_t x2 __asm__("x2") = a2;
    register uint64_t x3 __asm__("x3") = 0;
    __asm__ volatile("smc #0" : "+r"(x0), "+r"(x1), "+r"(x2), "+r"(x3)
                     :: "memory", "x4", "x5", "x6", "x7", "x8", "x9",
                        "x10", "x11", "x12", "x13", "x14", "x15", "x16", "x17");
    return {x0, x1, x2, x3};
}

static void liuqin_reset(void)
{
    __asm__ volatile("dsb sy" ::: "memory");
    (void)liuqin_smc(0x84000009u);
}

static int pong_halt_restart(unsigned int type)
{
    if (type == kPEPanicBegin || type == kPEPanicRestartCPU ||
        type == kPEPanicRestartCPUNoCallouts) {
        __atomic_store_n(&pong_panic_latched, 1, __ATOMIC_RELEASE);
        /* PanicBegin 发生在日志生成前，只能在收尾的 Restart 请求复位。 */
        if (type != kPEPanicBegin && liuqin_panic_reset) {
            if (pong_log_panic_flush) pong_log_panic_flush();
            liuqin_reset();
        }
        return pong_previous_halt_restart ? pong_previous_halt_restart(type) : -1;
    }
    if (type == kPEHaltCPU || type == kPERestartCPU) {
        if (__atomic_load_n(&pong_panic_latched, __ATOMIC_ACQUIRE)) {
            if (liuqin_panic_reset) {
                if (pong_log_panic_flush) pong_log_panic_flush();
                liuqin_reset();
            }
            return pong_previous_halt_restart ? pong_previous_halt_restart(type) : -1;
        }
        if (type == kPEHaltCPU && liuqin_halt_reset) type = kPERestartCPU;
        if (type == kPEHaltCPU && liuqin_pmic_poweroff) {
            const int result = liuqin_pmic_poweroff();
            IOLog("PongPSCI: PMIC power off result %d\n", result);
            if (result == 0) {
                for (;;) __asm__ volatile("wfi");
            }
        }
        (void)liuqin_smc(type == kPEHaltCPU ? 0x84000008u : 0x84000009u);
        return -1;
    }
    return pong_previous_halt_restart ? pong_previous_halt_restart(type) : -1;
}

static void liuqin_session_worker(void *, wait_result_t)
{
    clock_sec_t last_pet = 0;
    for (;;) {
        IOSleep(1000);
        if (__atomic_load_n(&pong_panic_latched, __ATOMIC_ACQUIRE)) continue;
        clock_sec_t seconds;
        clock_usec_t micros;
        clock_get_system_microtime(&seconds, &micros);
        if (liuqin_uptime && seconds >= liuqin_uptime) {
            IOLog("LIUQIN_SESSION: uptime deadline %u, reset after log flush\n", liuqin_uptime);
            /* UFS 控制台线程每秒落盘；留出完整刷写窗口避免丢失尾部日志。 */
            IOSleep(2500);
            liuqin_reset();
            liuqin_uptime = 0;
        }
        if (liuqin_wdt_pet && seconds - last_pet >= liuqin_wdt_pet) {
            int result = (int32_t)liuqin_smc(0x86000007u).a0;
            if (result) IOLog("LIUQIN_SESSION: watchdog ping failed %d\n", result);
            last_pet = seconds;
        }
    }
}

static void pong_halt_install(void)
{
    static uint32_t installed;
    if (__atomic_exchange_n(&installed, 1, __ATOMIC_ACQ_REL)) return;
    PE_parse_boot_argn("liuqin_panic_reset", &liuqin_panic_reset, sizeof(liuqin_panic_reset));
    PE_parse_boot_argn("liuqin_halt_reset", &liuqin_halt_reset, sizeof(liuqin_halt_reset));
    PE_parse_boot_argn("liuqin_uptime", &liuqin_uptime, sizeof(liuqin_uptime));
    PE_parse_boot_argn("liuqin_wdt_pet", &liuqin_wdt_pet, sizeof(liuqin_wdt_pet));
    uint32_t bite = 0;
    if (PE_parse_boot_argn("liuqin_wdt_bite", &bite, sizeof(bite))) {
        if (bite > 32 || (bite && liuqin_wdt_pet >= bite)) {
            IOLog("LIUQIN_SESSION: rejected watchdog parameters bite=%u pet=%u\n", bite, liuqin_wdt_pet);
            liuqin_wdt_pet = 0;
        } else {
            int result = (int32_t)liuqin_smc(0x86000005u, 2).a0;
            if (!result && bite) result = (int32_t)liuqin_smc(0x86000008u, bite * 1000, bite * 1000).a0;
            if (!result && bite) result = (int32_t)liuqin_smc(0x86000005u, 3).a0;
            IOLog("LIUQIN_SESSION: watchdog bite=%u result=%d\n", bite, result);
            if (!bite || result) liuqin_wdt_pet = 0;
        }
    }
    pong_previous_halt_restart = PE_halt_restart;
    PE_halt_restart = pong_halt_restart;
    if (liuqin_uptime || liuqin_wdt_pet) {
        thread_t thread = THREAD_NULL;
        kern_return_t result = kernel_thread_start(liuqin_session_worker, nullptr, &thread);
        if (result == KERN_SUCCESS) thread_deallocate(thread);
        IOLog("LIUQIN_SESSION: uptime=%u pet=%u worker=%d\n", liuqin_uptime, liuqin_wdt_pet, result);
    }
}

#endif
