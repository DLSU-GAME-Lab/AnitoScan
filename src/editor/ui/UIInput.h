#pragma once

#include <string>

enum class UIClick {
    None,
    CreateRun,
    SelectRun,
    SelectOutputModel,
    ExportAsset,
    StartRun,
    CancelRun,
    DeleteRun,
    SubmitSelection,
    NewRun,
    PreviousPhase,
    NextPhase,
    FollowLive,
    StopFollowingLive
};

struct UIInput {
    UIClick click = UIClick::None;
    std::string value;
};
