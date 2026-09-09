#include "resource_usage.h"

#include <sys/resource.h>
#include <limits>
#ifdef __linux__
#include <fstream>
#include <unistd.h>
#endif
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
#elif defined(__linux__)
    // statm reports current resident pages. getrusage reports peak KiB on Linux.
    std::ifstream statm("/proc/self/statm");
    unsigned long totalPages = 0, residentPages = 0;
    const long pageSize = sysconf(_SC_PAGESIZE);
    if (pageSize > 0 && statm >> totalPages >> residentPages) {
        return double(residentPages) * double(pageSize) / (1024.0 * 1024.0);
    }
#endif
    return std::numeric_limits<double>::quiet_NaN();
}

}  // namespace plotbench
