/**
 * useSimulation.js
 * Manages SSE flood simulation state and the EventSource lifecycle.
 */
import { useState, useRef, useCallback } from 'react';
import { API_URL } from '../config';

export function useSimulation() {
    const [isRunning, setIsRunning] = useState(false);
    const [isPaused, setIsPaused] = useState(false);
    const [currentStep, setCurrentStep] = useState(0);
    const [totalSteps, setTotalSteps] = useState(0);
    const [elapsedTime, setElapsedTime] = useState(0);
    const [simulationDone, setSimulationDone] = useState(false);
    const [floodData, setFloodData] = useState(null);
    const [roadsData, setRoadsData] = useState(null);   // sim-coloured roads
    const [evacuationPlan, setEvacuationPlan] = useState([]);
    const [shelterOccupancy, setShelterOccupancy] = useState({});
    const [finalReport, setFinalReport] = useState(null);
    const [statusMsg, setStatusMsg] = useState('Select a region to begin');

    const esRef = useRef(null);
    const pauseRef = useRef(false);
    const timerRef = useRef(null);

    const reset = useCallback(() => {
        esRef.current?.close(); esRef.current = null;
        clearInterval(timerRef.current); timerRef.current = null;
        setIsRunning(false); setIsPaused(false); pauseRef.current = false;
        setCurrentStep(0); setTotalSteps(0); setElapsedTime(0);
        setFloodData(null); setRoadsData(null);
        setEvacuationPlan([]); setShelterOccupancy({}); setFinalReport(null);
        setSimulationDone(false);
    }, []);

    const clearMap = useCallback(() => {
        setFloodData(null);
        setRoadsData(null);
    }, []);

    const start = useCallback((hobli, rainfallMm, steps, decayFactor, evacuationMode, useTraffic) => {
        reset();
        setIsRunning(true);
        setSimulationDone(false);
        setStatusMsg('Simulation running …');

        const t0 = Date.now();
        timerRef.current = setInterval(() => setElapsedTime(Math.round((Date.now() - t0) / 1000)), 1000);

        const params = new URLSearchParams({
            hobli,
            rainfall_mm: rainfallMm,
            steps,
            decay_factor: decayFactor,
            evacuation_mode: evacuationMode,
            use_traffic: useTraffic
        });
        const es = new EventSource(`${API_URL}/simulate-stream?${params}`);
        esRef.current = es;

        es.onmessage = async (evt) => {
            while (pauseRef.current) await new Promise(r => setTimeout(r, 200));
            const data = JSON.parse(evt.data);
            if (data.done) {
                es.close(); esRef.current = null;
                clearInterval(timerRef.current); timerRef.current = null;
                setIsRunning(false); setSimulationDone(true);
                if (data.summary) {
                    setFinalReport(data);
                    const evac = data.summary.total_evacuated || 0;
                    const statusSuffix = evac > 0 ? ` · ${evac.toLocaleString()} evacuated` : '';
                    setStatusMsg(`Done — ${data.total} steps${statusSuffix}`);
                } else {
                    setStatusMsg(`Done — ${data.total} steps`);
                }
                if (data.evacuation_plan?.length) setEvacuationPlan(data.evacuation_plan);
                return;
            }
            setCurrentStep(data.step);
            setTotalSteps(data.total);
            if (data.flood_geojson?.features?.length > 0) setFloodData(data.flood_geojson);
            if (data.roads_geojson?.features?.length > 0) setRoadsData(data.roads_geojson);
            // Evacuation plan only arrives in the final 'done' message - no-op here during streaming
        };

        es.onerror = () => {
            es.close(); esRef.current = null;
            clearInterval(timerRef.current); timerRef.current = null;
            setIsRunning(false);
            setStatusMsg('Stream error — check backend.');
        };
    }, [reset]);

    const togglePause = useCallback(() => {
        pauseRef.current = !pauseRef.current;
        setIsPaused(pauseRef.current);
        setStatusMsg(pauseRef.current ? 'Paused' : 'Simulation running …');
    }, []);

    const progressPct = totalSteps > 0 ? Math.round((currentStep / totalSteps) * 100) : 0;

    return {
        isRunning, isPaused, currentStep, totalSteps,
        elapsedTime, simulationDone, floodData, roadsData,
        evacuationPlan, shelterOccupancy, finalReport,
        statusMsg, setStatusMsg, progressPct,
        start, togglePause, reset, clearMap,
    };
}
