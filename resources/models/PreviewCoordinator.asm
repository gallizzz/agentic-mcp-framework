// Script-driven counterfactual preview checker for PGA.
// The .asmsh driver issues all hypothetical commands via run(PBPREVIEW,...).
// This ASM NEVER commands PBPREVIEW; it checks each completed hypothetical step.
// Trusted gap and goal constraints are provided by the experimental script.
// ASMETA range(a,b) excludes b. No predetermined limit on residual-plan length.
asm PreviewCoordinator

import StandardLibrary
import knowledge

signature:
    enum domain PCPhase = {PC_IDLE | PC_ACTIVE | PC_DONE}
    enum domain PreviewOutcome = {PREVIEW_NONE | PREVIEW_COMPATIBLE | PREVIEW_CONFLICT | PREVIEW_UNKNOWN}

    // Scheduler -> coordinator (the actual preview request metadata).
    monitored previewRequestId: Natural
    monitored previewBaseScheduleVersion: Natural
    monitored previewTargetCompartment: Compartment
    monitored previewTargetDoseIndex: Natural
    monitored previewCandidateTime: Natural

    // Script-driver instructions; NOT a hard-coded plan or an outcome.
    monitored previewBegin: Boolean
    monitored previewInspect: Boolean
    monitored previewFinalize: Boolean
    monitored previewReset: Boolean
    monitored previewExpectedCommandId: Natural
    monitored previewExpectedCompartment: Compartment
    monitored previewExpectedDoseIndex: Natural
    monitored previewExpectedTime: Natural

    // Trusted prescription minima; supplied at session start.
    monitored previewMinGap: Prod(Compartment,Compartment) -> Natural
    // Optional formalized per-step deadline (only when previewCheckGoal=true).
    monitored previewCheckGoal: Boolean
    monitored previewGoalCompartment: Compartment
    monitored previewGoalDoseIndex: Natural
    monitored previewGoalLatestTime: Natural

    // Actual outputs of the isolated Pillbox preview instance.
    monitored previewTime_consumption: Compartment -> Seq(Natural)
    monitored previewDrugIndex: Compartment -> Natural
    monitored previewScheduleVersion: Natural
    monitored previewLastAppliedCommandId: Compartment -> Natural
    monitored previewLastRejectedCommandId: Compartment -> Natural

    // Coordinator -> Scheduler (matching its monitored interface).
    out previewCompleted: Boolean
    out previewTimedOut: Boolean
    out previewResultRequestId: Natural
    out previewResultBaseVersion: Natural
    out previewOutcome: PreviewOutcome

    controlled pcPhase: PCPhase
    controlled pcRequestId: Natural
    controlled pcBaseVersion: Natural
    controlled pcLastVersion: Natural
    controlled pcStepsChecked: Natural
    controlled pcAllSafe: Boolean
    controlled pcUnknown: Boolean
    controlled pcGap: Prod(Compartment,Compartment) -> Natural

    derived pcPairSafe: Prod(Natural,Natural,Compartment,Compartment) -> Boolean
    derived pcScheduleSafe: Boolean
    derived pcCommandObserved: Boolean
    derived pcGoalSatisfied: Boolean

    static compartment1: Compartment
    static compartment2: Compartment

definitions:
    // Directed gap: if time(c) < time(d), use minGap(c,d).
    function pcPairSafe($t in Natural,$u in Natural,$c in Compartment,$d in Compartment) =
        if $t < $u then
            ($u >= $t + pcGap($c,$d))
        else
            if $t > $u then
                ($t >= $u + pcGap($d,$c))
            else
                false
            endif
        endif

    function pcScheduleSafe =
        (forall $c in Compartment with
            (forall $i in range(0n,iton(length(previewTime_consumption($c)))) with
                (forall $d in Compartment with
                    (forall $j in range(0n,iton(length(previewTime_consumption($d)))) with
                        (($c = $d and $i = $j) or
                         pcPairSafe(at(previewTime_consumption($c),$i),
                                    at(previewTime_consumption($d),$j),$c,$d))))))

    function pcCommandObserved =
        (previewExpectedCommandId != 0n and
         previewLastAppliedCommandId(previewExpectedCompartment) = previewExpectedCommandId and
         previewLastRejectedCommandId(previewExpectedCompartment) != previewExpectedCommandId and
         previewExpectedDoseIndex >= previewDrugIndex(previewExpectedCompartment) and
         previewExpectedDoseIndex < iton(length(previewTime_consumption(previewExpectedCompartment))) and
         previewScheduleVersion = pcLastVersion+1n and
         at(previewTime_consumption(previewExpectedCompartment),previewExpectedDoseIndex) = previewExpectedTime)

    function pcGoalSatisfied =
        (not previewCheckGoal or
         (previewGoalDoseIndex >= previewDrugIndex(previewGoalCompartment) and
          previewGoalDoseIndex < iton(length(previewTime_consumption(previewGoalCompartment))) and
          at(previewTime_consumption(previewGoalCompartment),previewGoalDoseIndex) <= previewGoalLatestTime))

    rule r_Begin =
        if previewRequestId != 0n and
           previewScheduleVersion = previewBaseScheduleVersion and
           previewTargetDoseIndex >= previewDrugIndex(previewTargetCompartment) and
           previewTargetDoseIndex < iton(length(previewTime_consumption(previewTargetCompartment))) then
            par
                pcRequestId := previewRequestId
                pcBaseVersion := previewBaseScheduleVersion
                pcLastVersion := previewScheduleVersion
                pcStepsChecked := 0n
                pcAllSafe := true
                pcUnknown := false
                forall $c in Compartment do
                    forall $d in Compartment do
                        pcGap($c,$d) := previewMinGap($c,$d)
                pcPhase := PC_ACTIVE
                previewCompleted := false
                previewTimedOut := false
                previewOutcome := PREVIEW_NONE
                previewResultRequestId := previewRequestId
                previewResultBaseVersion := previewBaseScheduleVersion
            endpar
        else
            par
                pcPhase := PC_DONE
                previewCompleted := true
                previewTimedOut := false
                previewOutcome := PREVIEW_UNKNOWN
                previewResultRequestId := previewRequestId
                previewResultBaseVersion := previewBaseScheduleVersion
            endpar
        endif

    // The script has already executed ONE action on PBPREVIEW.
    // This step checks the resulting snapshot and latches any safety failure.
    rule r_Inspect =
        par
            if not pcCommandObserved then
                pcUnknown := true
            endif
            if not pcScheduleSafe or not pcGoalSatisfied then
                pcAllSafe := false
            endif
            pcLastVersion := previewScheduleVersion
            pcStepsChecked := pcStepsChecked+1n
        endpar

    rule r_Finish =
        par
            previewCompleted := true
            previewTimedOut := false
            previewResultRequestId := pcRequestId
            previewResultBaseVersion := pcBaseVersion
            if pcStepsChecked = 0n or pcUnknown then
                previewOutcome := PREVIEW_UNKNOWN
            else
                if pcAllSafe and pcGoalSatisfied and pcScheduleSafe then
                    previewOutcome := PREVIEW_COMPATIBLE
                else
                    previewOutcome := PREVIEW_CONFLICT
                endif
            endif
            pcPhase := PC_DONE
        endpar

    main rule r_Main =
        if pcPhase = PC_IDLE then
            if previewBegin then
                r_Begin[]
            endif
        else
            if pcPhase = PC_ACTIVE then
                if previewInspect then
                    r_Inspect[]
                else
                    if previewFinalize then
                        r_Finish[]
                    endif
                endif
            else
                if pcPhase = PC_DONE and previewReset then
                    par
                        pcPhase := PC_IDLE
                        previewCompleted := false
                        previewOutcome := PREVIEW_NONE
                    endpar
                endif
            endif
        endif

default init s0:
    function pcPhase = PC_IDLE
    function pcRequestId = 0n
    function pcBaseVersion = 0n
    function pcLastVersion = 0n
    function pcStepsChecked = 0n
    function pcAllSafe = true
    function pcUnknown = false
    function pcGap($c in Compartment,$d in Compartment) = 0n
    function previewCompleted = false
    function previewTimedOut = false
    function previewResultRequestId = 0n
    function previewResultBaseVersion = 0n
    function previewOutcome = PREVIEW_NONE
