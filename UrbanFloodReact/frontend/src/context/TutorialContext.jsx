import React, { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react';
import {
  loginSteps,
  researcherSteps,
  authoritySteps,
  citizenSteps,
  simulateSteps,
} from '../data/tutorialSteps';

const TutorialContext = createContext(null);

const stepsByMode = {
  login: loginSteps,
  researcher: researcherSteps,
  authority: authoritySteps,
  citizen: citizenSteps,
  simulate: simulateSteps,
};

export function TutorialProvider({ children }) {
  const [active, setActive] = useState(false);
  const [mode, setMode] = useState(null);           // 'login' | 'researcher' | ...
  const [stepIndex, setStepIndex] = useState(0);
  const onTabSwitchRef = useRef(null);               // callback to auto-switch sidebar tabs

  const steps = mode ? (stepsByMode[mode] || []) : [];
  const currentStep = steps[stepIndex] || null;

  // Register a tab-switch handler from the host component
  const registerTabSwitch = useCallback((fn) => {
    onTabSwitchRef.current = fn;
  }, []);

  // Start a tutorial for a given mode
  const startTutorial = useCallback((tutorialMode) => {
    if (!stepsByMode[tutorialMode]) return;
    setMode(tutorialMode);
    setStepIndex(0);
    setActive(true);
  }, []);

  // Navigate
  const nextStep = useCallback(() => {
    setStepIndex((prev) => {
      const next = prev + 1;
      if (next >= steps.length) {
        setActive(false);
        setMode(null);
        return 0;
      }
      // Auto-switch tab if the next step requires it
      const nextStepDef = steps[next];
      if (nextStepDef?.tab && onTabSwitchRef.current) {
        onTabSwitchRef.current(nextStepDef.tab);
      }
      return next;
    });
  }, [steps]);

  const prevStep = useCallback(() => {
    setStepIndex((prev) => {
      const next = Math.max(0, prev - 1);
      const prevStepDef = steps[next];
      if (prevStepDef?.tab && onTabSwitchRef.current) {
        onTabSwitchRef.current(prevStepDef.tab);
      }
      return next;
    });
  }, [steps]);

  const skipTutorial = useCallback(() => {
    setActive(false);
    setMode(null);
    setStepIndex(0);
  }, []);

  const goToStep = useCallback((idx) => {
    if (idx >= 0 && idx < steps.length) {
      setStepIndex(idx);
      const stepDef = steps[idx];
      if (stepDef?.tab && onTabSwitchRef.current) {
        onTabSwitchRef.current(stepDef.tab);
      }
    }
  }, [steps]);

  // When active changes or step changes, auto-switch tab
  useEffect(() => {
    if (active && currentStep?.tab && onTabSwitchRef.current) {
      onTabSwitchRef.current(currentStep.tab);
    }
  }, [active, stepIndex]);

  const value = {
    active,
    mode,
    stepIndex,
    steps,
    currentStep,
    totalSteps: steps.length,
    startTutorial,
    nextStep,
    prevStep,
    skipTutorial,
    goToStep,
    registerTabSwitch,
  };

  return (
    <TutorialContext.Provider value={value}>
      {children}
    </TutorialContext.Provider>
  );
}

export function useTutorial() {
  const ctx = useContext(TutorialContext);
  if (!ctx) {
    throw new Error('useTutorial must be used within a TutorialProvider');
  }
  return ctx;
}
