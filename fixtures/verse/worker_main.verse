# Standalone test adapter. The runner combines this with ui_controller.verse.
# Yield/Print/Exit here are VerseCmd native APIs, not UEFN APIs.
Main(Args:[]string, Env:[string]string)<suspends>:void =
    Model := ui_controller{}
    spawn{Model.Listen()}
    Yield()
    if (Model.Clicks <> 0):
        Exit(10)
    Model.Click.Signal(true)
    Yield()
    if (Model.Pressed?, Model.Clicks = 1):
        Print("RIVE_TEST event_resume PASS")
    else:
        Exit(11)

    # No second awaiter: a recurring event must not replay an earlier signal.
    Model.Click.Signal(false)
    spawn{Model.Listen()}
    Yield()
    if (Model.Pressed?, Model.Clicks = 1):
        Print("RIVE_TEST event_no_sticky_replay PASS")
    else:
        Exit(12)

    spawn{Model.RunUntilStopped()}
    Yield()
    if (Model.Entered = 1, Model.Cancelled = 0, Model.LateWrites = 0):
        Print("RIVE_TEST suspended PASS")
    else:
        Exit(13)
    Model.Stop.Signal()
    Yield()
    Model.Late.Signal()
    Yield()
    if (Model.Cancelled = 1, Model.LateWrites = 0):
        Print("RIVE_TEST race_cancel_defer_no_late_resume PASS")
    else:
        Exit(14)

    if (Model.SpeculativeChange[]):
        Exit(15)
    if (Model.Pressed?, Model.Clicks = 1):
        Print("RIVE_TEST failure_rollback PASS")
    else:
        Exit(16)
    if (Mode := Args[1], Mode = "idle"):
        Model.Click.Signal(false)
        Yield()
        if (not Model.Pressed?, Model.Clicks = 2):
            Print("RIVE_TEST second_ui_event PASS")
        else:
            Exit(17)
    if (Model.Pressed?):
        Print("RIVE_UI bool Pressed true")
    else:
        Print("RIVE_UI bool Pressed false")
    Print("RIVE_TEST all PASS")
