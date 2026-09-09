// Process CPU share and resident memory for the HUD, without any Python dependency.
#pragma once

#include <QElapsedTimer>

namespace plotbench {

class ResourceUsage {
public:
    ResourceUsage();
    double cpuPercent();       // CPU time delta over wall time since the previous call
    double residentMiB() const;

private:
    QElapsedTimer m_wall;
    double m_cpuSeconds = 0;
    static double processCpuSeconds();
};

}  // namespace plotbench
