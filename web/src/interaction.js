import { useEffect } from "react";

// Motion is local to the hovered control. No permanent render loop or custom cursor.
export function useInteractionFeedback(page) {
  useEffect(() => {
    const fine = matchMedia("(hover: hover) and (pointer: fine)");
    const reduced = matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0;
    let activeTitle = null;
    let activeCard = null;
    let point = null;
    const clear = () => {
      if (activeTitle) activeTitle.removeAttribute("data-pointer");
      activeTitle = null;
      if (activeCard) activeCard.removeAttribute("data-pointer");
      activeCard = null;
      cancelAnimationFrame(frame);
      frame = 0;
    };
    const draw = () => {
      frame = 0;
      if (!point || !fine.matches || reduced.matches || document.hidden)
        return clear();
      const target = point.target instanceof Element ? point.target : null;
      const title = target?.closest(".interactive-title");
      if (activeTitle && activeTitle !== title)
        activeTitle.removeAttribute("data-pointer");
      activeTitle = title;
      const card = target?.closest(".rule-object");
      if (activeCard && activeCard !== card)
        activeCard.removeAttribute("data-pointer");
      activeCard = card;
      if (card) {
        const box = card.getBoundingClientRect();
        card.style.setProperty(
          "--tilt-x",
          `${(-(point.y - box.top - box.height / 2) / box.height) * 8}deg`,
        );
        card.style.setProperty(
          "--tilt-y",
          `${((point.x - box.left - box.width / 2) / box.width) * 10}deg`,
        );
        card.setAttribute("data-pointer", "true");
      }
      for (const node of [target?.closest("button"), title]) {
        if (!node) continue;
        const bounds = node.getBoundingClientRect();
        node.style.setProperty("--pointer-x", `${point.x - bounds.left}px`);
        node.style.setProperty("--pointer-y", `${point.y - bounds.top}px`);
      }
      title?.setAttribute("data-pointer", "true");
    };
    const move = (event) => {
      if (!fine.matches || reduced.matches) return;
      point = { x: event.clientX, y: event.clientY, target: event.target };
      if (!frame) frame = requestAnimationFrame(draw);
    };
    document.addEventListener("pointermove", move, { passive: true });
    document.addEventListener("pointerleave", clear);
    document.addEventListener("visibilitychange", clear);
    window.addEventListener("scroll", clear, { passive: true });
    reduced.addEventListener("change", clear);
    return () => {
      clear();
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerleave", clear);
      document.removeEventListener("visibilitychange", clear);
      window.removeEventListener("scroll", clear);
      reduced.removeEventListener("change", clear);
    };
  }, [page]);
}
