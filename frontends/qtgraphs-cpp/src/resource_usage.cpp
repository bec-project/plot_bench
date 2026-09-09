#include "resource_usage.h"

#include <sys/resource.h>
#ifdef __APPLE__
#include <mach/mach.h>
#endif

namespace plotbench {

ResourceUsage::ResourceUsage() {
    m_wall.start();
    m_cpuSeconds = processCpuSeconds();
}

double ResourceUsage::processCpuSeconds() {
    rusage usage{};
    getrusage(RUSAGE_SELF, &usage);
    return double(usage.ru_utime.tv_sec) + double(usage.ru_utime.tv_usec) / 1e6 + double(usage.ru_stime.tv_sec)
           + double(usage.ru_stime.tv_usec) / 1e6;
}

double ResourceUsage::cpuPercent() {
    const double wall = m_wall.nsecsElapsed() / 1e9;
    const double cpu = processCpuSeconds();
    const double percent = wall > 0 ? (cpu - m_cpuSeconds) / wall * 100.0 : 0;
    m_wall.restart();
    m_cpuSeconds = cpu;
    return percent;
}

double ResourceUsage::residentMiB() const {
#ifdef __APPLE__
    mach_task_basic_info info{};
    mach_msg_type_number_t count = MACH_TASK_BASIC_INFO_COUNT;
    if (task_info(mach_task_self(), MACH_TASK_BASIC_INFO, reinterpret_cast<task_info_t>(&info), &count) == KERN_SUCCESS) {
        return double(info.resident_size) / (1024.0 * 1024.0);
    }
#endif
    rusage usage{};
    getrusage(RUSAGE_SELF, &usage);
    return double(usage.ru_maxrss) / (1024.0 * 1024.0);
}

}  // namespace plotbench
