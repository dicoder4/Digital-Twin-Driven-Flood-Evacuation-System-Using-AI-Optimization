/**
 * SimulationControls.jsx
 * Steps, decay sliders + Run / Pause / Reset buttons + progress bar.
 */
import { Play, Pause, RefreshCw, Clock, Activity } from 'lucide-react';

export function SimulationControls({
    steps, decayFactor,
    onSteps, onDecay,
    isRunning, isPaused, simulationDone,
    currentStep, totalSteps, elapsedTime, progressPct,
    onStart, onTogglePause, onReset,
}) {
    return (
        <section className="panel">
            <h3 className="panel-title"><Activity size={13} /> Simulation</h3>

            <label className="field-label">Steps — {steps}</label>
            <input
                type="range" min={5} max={50} step={1}
                value={steps} onChange={e => onSteps(Number(e.target.value))}
                className="slider"
            />

            <label className="field-label">Decay Factor — {decayFactor.toFixed(2)}</label>
            <input
                type="range" min={0.1} max={0.9} step={0.05}
                value={decayFactor} onChange={e => onDecay(Number(e.target.value))}
                className="slider"
            />

            <div className="btn-row">
                {!isRunning
                    ? <button className="btn-primary" onClick={onStart}><Play size={13} /> Run Simulation</button>
                    : <button className="btn-secondary" onClick={onTogglePause}>
                        {isPaused ? <><Play size={13} /> Resume</> : <><Pause size={13} /> Pause</>}
                    </button>}
                <button
                    className="btn-ghost"
                    onClick={onReset}
                    disabled={!isRunning && !simulationDone}
                >
                    <RefreshCw size={13} /> Reset
                </button>
            </div>

            {(isRunning || simulationDone) && (
                <div className="progress-section">
                    <div className="progress-bar-bg">
                        <div className="progress-bar-fill" style={{ width: `${progressPct}%` }} />
                    </div>
                    <div className="progress-stats">
                        <span><Clock size={10} /> {elapsedTime}s</span>
                        <span>{currentStep}/{totalSteps} ({progressPct}%)</span>
                    </div>
                </div>
            )}
        </section>
    );
}
