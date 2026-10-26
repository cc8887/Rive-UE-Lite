# Shared business logic: no Fortnite device, UMG or worker-only native calls.
using { /Verse.org/Concurrency }

ui_controller := class:
    Click:event(logic) = event(logic){}
    Stop:event() = event(){}
    Late:event() = event(){}
    var Pressed:logic = false
    var Clicks:int = 0
    var Entered:int = 0
    var Cancelled:int = 0
    var LateWrites:int = 0

    Listen()<suspends>:void =
        Value := Click.Await()
        set Pressed = Value
        set Clicks += 1

    WaitForWork()<suspends>:void =
        set Entered += 1
        defer:
            set Cancelled += 1
        Late.Await()
        set LateWrites += 1

    RunUntilStopped()<suspends>:void =
        race:
            WaitForWork()
            Stop.Await()

    SpeculativeChange()<transacts><decides>:void =
        set Pressed = false
        set Clicks = 999
        false?
