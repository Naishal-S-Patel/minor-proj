import { useState, useEffect, type RefObject } from "react";

export function useIntersectionObserver(
  ref: RefObject<Element>,
  options: IntersectionObserverInit = { threshold: 0.15 },
): boolean {
  const [isVisible, setIsVisible] = useState(false);
  useEffect(() => {
    if (!ref.current) return;
    const obs = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setIsVisible(true);
        obs.disconnect();
      }
    }, options);
    obs.observe(ref.current);
    return () => obs.disconnect();
  }, [ref, options.threshold]);
  return isVisible;
}
