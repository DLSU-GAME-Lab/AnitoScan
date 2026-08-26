#pragma once

#include <string>

enum class UIClick {
    None,
    CreateRun,
    SelectRun,
    StartRun,
    CancelRun,
    DeleteRun,
    SubmitSelection,
    NewRun,
    PreviousPhase,
    NextPhase,
    FollowLive
};

struct UIInput {
    UIClick click = UIClick::None;
    std::string value;
};
