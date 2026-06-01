import React, { useEffect, useRef, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useTutorial } from '../context/TutorialContext';
import { useLanguage } from '../context/LanguageContext';
import '../styles/tutorial.css';

/**
 * TutorialOverlay — renders the spotlight + tooltip as a portal.
 * Auto-positions tooltip, scrolls target into view, supports keyboard nav.
 * Supports bilingual (English / Kannada) via LanguageContext.
 */
export default function TutorialOverlay() {
  const {
    active, currentStep, stepIndex, totalSteps,
    nextStep, prevStep, skipTutorial,
  } = useTutorial();

  const { lang } = useLanguage();

  const [targetRect, setTargetRect] = useState(null);
  const [tooltipStyle, setTooltipStyle] = useState({});
  const [arrowClass, setArrowClass] = useState('');
  const overlayRef = useRef(null);
  const tooltipRef = useRef(null);

  // ── Get translated step content ────────────────────────────────────
  const getTitle = (step) => {
    if (!step) return '';
    return lang === 'kn' && step.title_kn ? step.title_kn : step.title;
  };

  const getContent = (step) => {
    if (!step) return '';
    return lang === 'kn' && step.content_kn ? step.content_kn : step.content;
  };

  // ── UI labels ──────────────────────────────────────────────────────
  const labels = {
    skip: lang === 'kn' ? 'ಬಿಡಿ' : 'Skip',
    back: lang === 'kn' ? '← ಹಿಂದೆ' : '← Back',
    next: lang === 'kn' ? 'ಮುಂದೆ →' : 'Next →',
    finish: lang === 'kn' ? 'ಮುಗಿಸಿ ✓' : 'Finish ✓',
  };

  // ── Measure target element position ──────────────────────────────
  const measureTarget = useCallback(() => {
    if (!currentStep?.target) {
      setTargetRect(null);
      return;
    }
    const el = document.querySelector(currentStep.target);
    if (!el) {
      setTargetRect(null);
      return;
    }
    // Scroll into view first
    el.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });

    // Small delay to let scroll settle
    requestAnimationFrame(() => {
      const rect = el.getBoundingClientRect();
      const padding = currentStep.spotlightPadding ?? 8;
      setTargetRect({
        top: rect.top - padding,
        left: rect.left - padding,
        width: rect.width + padding * 2,
        height: rect.height + padding * 2,
        rawTop: rect.top,
        rawLeft: rect.left,
        rawWidth: rect.width,
        rawHeight: rect.height,
      });
    });
  }, [currentStep]);

  // Re-measure on step change, on scroll, and on resize
  useEffect(() => {
    if (!active) return;
    measureTarget();

    const handleReposition = () => measureTarget();
    window.addEventListener('resize', handleReposition);
    window.addEventListener('scroll', handleReposition, true);

    // Re-measure periodically in case of late renders / animations
    const interval = setInterval(handleReposition, 500);

    return () => {
      window.removeEventListener('resize', handleReposition);
      window.removeEventListener('scroll', handleReposition, true);
      clearInterval(interval);
    };
  }, [active, stepIndex, measureTarget]);

  // ── Position tooltip relative to spotlight ──────────────────────
  useEffect(() => {
    if (!active) return;

    // No target → centered modal
    if (!currentStep?.target || !targetRect) {
      setTooltipStyle({
        position: 'fixed',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        maxWidth: '440px',
        width: '90vw',
      });
      setArrowClass('');
      return;
    }

    const margin = 16;
    const tooltipEl = tooltipRef.current;
    const tooltipW = tooltipEl?.offsetWidth || 360;
    const tooltipH = tooltipEl?.offsetHeight || 200;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    let placement = currentStep.placement || 'right';
    let style = {};
    let arrow = '';

    // Try preferred placement, fallback if off-screen
    const tryPlace = (dir) => {
      switch (dir) {
        case 'right': {
          const left = targetRect.left + targetRect.width + margin;
          const top = targetRect.top + targetRect.height / 2 - tooltipH / 2;
          if (left + tooltipW < vw && top > 0 && top + tooltipH < vh) {
            return { style: { position: 'fixed', left, top: Math.max(8, top) }, arrow: 'tutorial-arrow-left' };
          }
          return null;
        }
        case 'left': {
          const left = targetRect.left - tooltipW - margin;
          const top = targetRect.top + targetRect.height / 2 - tooltipH / 2;
          if (left > 0 && top > 0 && top + tooltipH < vh) {
            return { style: { position: 'fixed', left, top: Math.max(8, top) }, arrow: 'tutorial-arrow-right' };
          }
          return null;
        }
        case 'bottom': {
          const top = targetRect.top + targetRect.height + margin;
          const left = targetRect.left + targetRect.width / 2 - tooltipW / 2;
          if (top + tooltipH < vh && left > 0 && left + tooltipW < vw) {
            return { style: { position: 'fixed', top, left: Math.max(8, left) }, arrow: 'tutorial-arrow-top' };
          }
          return null;
        }
        case 'top': {
          const top = targetRect.top - tooltipH - margin;
          const left = targetRect.left + targetRect.width / 2 - tooltipW / 2;
          if (top > 0 && left > 0 && left + tooltipW < vw) {
            return { style: { position: 'fixed', top, left: Math.max(8, left) }, arrow: 'tutorial-arrow-bottom' };
          }
          return null;
        }
        default:
          return null;
      }
    };

    const order = [placement, 'right', 'bottom', 'left', 'top'];
    for (const dir of order) {
      const result = tryPlace(dir);
      if (result) {
        style = result.style;
        arrow = result.arrow;
        break;
      }
    }

    // Fallback: just center it
    if (!style.position) {
      style = {
        position: 'fixed',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
      };
      arrow = '';
    }

    setTooltipStyle({ ...style, maxWidth: '400px', width: '90vw' });
    setArrowClass(arrow);
  }, [active, currentStep, targetRect]);

  // ── Keyboard navigation ──────────────────────────────────────────
  useEffect(() => {
    if (!active) return;
    const handleKey = (e) => {
      if (e.key === 'ArrowRight' || e.key === 'Enter') { e.preventDefault(); nextStep(); }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); prevStep(); }
      else if (e.key === 'Escape') { e.preventDefault(); skipTutorial(); }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [active, nextStep, prevStep, skipTutorial]);

  if (!active || !currentStep) return null;

  const progressPct = totalSteps > 0 ? ((stepIndex + 1) / totalSteps) * 100 : 0;
  const isFirst = stepIndex === 0;
  const isLast = stepIndex === totalSteps - 1;

  const title = getTitle(currentStep);
  const content = getContent(currentStep);

  // Generate clip-path for spotlight cutout
  const clipPath = targetRect
    ? `polygon(
        0% 0%, 0% 100%, 
        ${targetRect.left}px 100%, 
        ${targetRect.left}px ${targetRect.top}px, 
        ${targetRect.left + targetRect.width}px ${targetRect.top}px, 
        ${targetRect.left + targetRect.width}px ${targetRect.top + targetRect.height}px, 
        ${targetRect.left}px ${targetRect.top + targetRect.height}px, 
        ${targetRect.left}px 100%, 
        100% 100%, 100% 0%
      )`
    : 'none';

  return createPortal(
    <div className="tutorial-overlay" ref={overlayRef}>
      {/* Dark mask with spotlight cutout */}
      <div
        className="tutorial-mask"
        style={{ clipPath }}
        onClick={(e) => { e.stopPropagation(); skipTutorial(); }}
      />

      {/* Spotlight ring (glowing border) */}
      {targetRect && (
        <div
          className="tutorial-spotlight-ring"
          style={{
            top: targetRect.top,
            left: targetRect.left,
            width: targetRect.width,
            height: targetRect.height,
          }}
        />
      )}

      {/* Tooltip */}
      <div
        className={`tutorial-tooltip ${arrowClass}`}
        style={tooltipStyle}
        ref={tooltipRef}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Progress bar */}
        <div className="tutorial-progress-bar">
          <div
            className="tutorial-progress-fill"
            style={{ width: `${progressPct}%` }}
          />
        </div>

        {/* Content */}
        <div className="tutorial-tooltip-content">
          <h3 className="tutorial-tooltip-title">{title}</h3>
          <p className="tutorial-tooltip-text">
            {content.split('\n').map((line, i) => (
              <React.Fragment key={i}>
                {line}
                {i < content.split('\n').length - 1 && <br />}
              </React.Fragment>
            ))}
          </p>
        </div>

        {/* Footer */}
        <div className="tutorial-tooltip-footer">
          <span className="tutorial-step-counter">
            {stepIndex + 1} / {totalSteps}
          </span>
          <div className="tutorial-tooltip-actions">
            <button
              className="tutorial-btn tutorial-btn-skip"
              onClick={skipTutorial}
            >
              {labels.skip}
            </button>
            {!isFirst && (
              <button
                className="tutorial-btn tutorial-btn-prev"
                onClick={prevStep}
              >
                {labels.back}
              </button>
            )}
            <button
              className="tutorial-btn tutorial-btn-next"
              onClick={nextStep}
            >
              {isLast ? labels.finish : labels.next}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
