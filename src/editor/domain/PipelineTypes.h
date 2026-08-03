#pragma once

#include <string>

using RunId = std::string;

enum class RunStatus { Pending, Running, Completed, Failed, Cancelled };
enum class PipelinePhase { Capture, Masking, Spatial, Geometry, Export };
