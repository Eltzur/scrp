import { useEffect, useId, useState } from 'react';

type Variant = 'hero' | 'header' | 'favicon';
type Lang    = 'he' | 'en';

export interface XxlLogoProps {
  variant?:     Variant;
  lang?:        Lang;
  forceStatic?: boolean;
  className?:   string;
}

const SESSION_KEY = 'xxl_animated_this_session';

// Full animation CSS — injected inline with the SVG so it's self-contained.
// These class-scoped selectors only fire when the parent SVG carries .xxl-anim.
const ANIM_CSS = `
  @keyframes xxlStreakL {
    0%   { transform: translateX(-280px); opacity: 0; }
    60%  { opacity: 1; }
    100% { transform: translateX(0); opacity: 1; }
  }
  @keyframes xxlStreakR {
    0%   { transform: translateX(280px); opacity: 0; }
    60%  { opacity: 1; }
    100% { transform: translateX(0); opacity: 1; }
  }
  @keyframes xxlSlamHard {
    0%, 49% { transform: scale(0.35) translateY(-40px); opacity: 0; }
    50%  { transform: scale(1.85) translateY(0); opacity: 1; }
    56%  { transform: scale(0.78) translateY(12px); }
    64%  { transform: scale(1.18) translateY(-7px); }
    72%  { transform: scale(0.94) translateY(3px); }
    82%  { transform: scale(1.04) translateY(-1px); }
    100% { transform: scale(1) translateY(0); opacity: 1; }
  }
  @keyframes xxlShadowFollowHard {
    0%, 50% { opacity: 0; transform: scale(0.35); }
    56%  { opacity: 0.8; transform: scale(1.2); }
    100% { opacity: 1; transform: scale(1); }
  }
  @keyframes xxlFlashImpactHard {
    0%, 49% { opacity: 0; }
    50%  { opacity: 0.95; }
    56%  { opacity: 0.4; }
    62%  { opacity: 0; }
    100% { opacity: 0; }
  }
  @keyframes xxlCameraShakeHard {
    0%, 49% { transform: translate(0,0); }
    50%  { transform: translate(-7px,4px); }
    53%  { transform: translate(6px,-5px); }
    56%  { transform: translate(-5px,3px); }
    59%  { transform: translate(4px,-2px); }
    62%  { transform: translate(-2px,1px); }
    65%, 100% { transform: translate(0,0); }
  }
  @keyframes xxlTaglineAppear {
    0%, 75% { opacity: 0; transform: translateY(-8px); }
    100%    { opacity: 1; transform: translateY(0); }
  }

  .xxl-anim .xxl-streak-l-1 { animation: xxlStreakL 0.40s cubic-bezier(0.2,0.8,0.2,1) 0s both; }
  .xxl-anim .xxl-streak-l-2 { animation: xxlStreakL 0.40s cubic-bezier(0.2,0.8,0.2,1) 0.06s both; }
  .xxl-anim .xxl-streak-l-3 { animation: xxlStreakL 0.40s cubic-bezier(0.2,0.8,0.2,1) 0.12s both; }
  .xxl-anim .xxl-streak-r-1 { animation: xxlStreakR 0.40s cubic-bezier(0.2,0.8,0.2,1) 0s both; }
  .xxl-anim .xxl-streak-r-2 { animation: xxlStreakR 0.40s cubic-bezier(0.2,0.8,0.2,1) 0.06s both; }
  .xxl-anim .xxl-streak-r-3 { animation: xxlStreakR 0.40s cubic-bezier(0.2,0.8,0.2,1) 0.12s both; }
  .xxl-anim .xxl-shadow  { animation: xxlShadowFollowHard 1.5s cubic-bezier(0.5,-0.5,0.2,1.4) 0.45s both; transform-origin: 348px 220px; }
  .xxl-anim .xxl-front   { animation: xxlSlamHard         1.5s cubic-bezier(0.5,-0.5,0.2,1.4) 0.45s both; transform-origin: 340px 215px; }
  .xxl-anim .xxl-flash   { animation: xxlFlashImpactHard  1.5s ease-out 0.45s both; }
  .xxl-anim .xxl-shake   { animation: xxlCameraShakeHard  1.5s ease-out 0.45s both; transform-origin: center; }
  .xxl-anim .xxl-tagline { animation: xxlTaglineAppear    0.7s cubic-bezier(0.2,0.8,0.2,1) 1.45s both; }

  .xxl-static .xxl-streak-l-1, .xxl-static .xxl-streak-l-2, .xxl-static .xxl-streak-l-3,
  .xxl-static .xxl-streak-r-1, .xxl-static .xxl-streak-r-2, .xxl-static .xxl-streak-r-3,
  .xxl-static .xxl-shadow, .xxl-static .xxl-front, .xxl-static .xxl-tagline {
    opacity: 1;
    transform: none;
  }
  .xxl-static .xxl-flash { opacity: 0; }
`;

export default function XxlLogo({
  variant     = 'hero',
  lang        = 'he',
  forceStatic = false,
  className,
}: XxlLogoProps) {
  // useId returns values like ":r0:" — sanitise for use as SVG id attributes
  const rawId = useId();
  const uid   = rawId.replace(/[^a-zA-Z0-9]/g, '');
  const arcId = `xxl-arc-${uid}`;

  // Default to static to avoid a flash of unanimated content on first render.
  // The effect runs after mount and promotes to 'xxl-anim' if this is the
  // first visit this session.
  const [animClass, setAnimClass] = useState<'xxl-anim' | 'xxl-static'>('xxl-static');

  useEffect(() => {
    if (variant !== 'hero' || forceStatic) return;
    if (!sessionStorage.getItem(SESSION_KEY)) {
      setAnimClass('xxl-anim');
      sessionStorage.setItem(SESSION_KEY, '1');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // intentionally empty — run once on mount only

  // Favicon variant: stripped-down wordmark, tight viewBox, no animation
  if (variant === 'favicon') {
    return (
      <svg
        viewBox="0 0 320 200"
        xmlns="http://www.w3.org/2000/svg"
        className={className}
        aria-label="XXL"
      >
        <text
          x="168" y="155"
          fontFamily="Rubik, Arial Black, sans-serif"
          fontWeight="900" fontSize="160" fill="#064E3B"
          textAnchor="middle" fontStyle="italic" letterSpacing="-4"
        >XXL</text>
        <text
          x="160" y="150"
          fontFamily="Rubik, Arial Black, sans-serif"
          fontWeight="900" fontSize="160" fill="#059669"
          textAnchor="middle" fontStyle="italic" letterSpacing="-4"
        >XXL</text>
      </svg>
    );
  }

  // Full logo (hero + header share the same SVG markup; only the CSS class differs)
  const svgClass = (variant !== 'hero' || forceStatic) ? 'xxl-static' : animClass;
  const combined = [svgClass, className].filter(Boolean).join(' ');
  const isHero   = variant === 'hero';

  const tagline = lang === 'he' ? (
    <g className="xxl-tagline">
      <path id={arcId} d="M 130 130 Q 340 70 550 130" fill="none" stroke="none" />
      <text
        fontFamily="Rubik, Arial, sans-serif"
        fontWeight="900" fontSize="42" fill="#EA580C" letterSpacing="2"
      >
        <textPath href={`#${arcId}`} startOffset="50%" textAnchor="middle">
          חוסכים בענקקק
        </textPath>
      </text>
    </g>
  ) : (
    <g className="xxl-tagline">
      <path id={arcId} d="M 130 130 Q 340 70 550 130" fill="none" stroke="none" />
      <text fontFamily="Rubik, Arial, sans-serif" fontWeight="900" fill="#EA580C" letterSpacing="3">
        <textPath href={`#${arcId}`} startOffset="50%" textAnchor="middle">
          <tspan fontSize="32">SAVING </tspan><tspan fontSize="64">BIG</tspan>
        </textPath>
      </text>
    </g>
  );

  return (
    <svg
      viewBox="0 0 680 320"
      xmlns="http://www.w3.org/2000/svg"
      className={combined}
      aria-label={lang === 'he' ? 'XXL — חוסכים בענקקק' : 'XXL — SAVING BIG'}
    >
      <style>{ANIM_CSS}</style>

      <g className="xxl-shake">
        {/* Speed lines — hero only */}
        {isHero && (
          <>
            <line className="xxl-streak-l-1" x1="35"  y1="195" x2="115" y2="195" stroke="#EA580C" strokeWidth="7" strokeLinecap="round" opacity="0.4"  />
            <line className="xxl-streak-l-2" x1="50"  y1="220" x2="130" y2="220" stroke="#EA580C" strokeWidth="7" strokeLinecap="round" opacity="0.65" />
            <line className="xxl-streak-l-3" x1="65"  y1="245" x2="145" y2="245" stroke="#EA580C" strokeWidth="7" strokeLinecap="round" opacity="0.9"  />
            <line className="xxl-streak-r-1" x1="565" y1="195" x2="645" y2="195" stroke="#059669" strokeWidth="7" strokeLinecap="round" opacity="0.9"  />
            <line className="xxl-streak-r-2" x1="550" y1="220" x2="630" y2="220" stroke="#059669" strokeWidth="7" strokeLinecap="round" opacity="0.65" />
            <line className="xxl-streak-r-3" x1="535" y1="245" x2="615" y2="245" stroke="#059669" strokeWidth="7" strokeLinecap="round" opacity="0.4"  />
          </>
        )}

        {/* Shadow + front wordmark */}
        <text
          className="xxl-shadow"
          x="348" y="271"
          fontFamily="Rubik, Arial, sans-serif"
          fontWeight="900" fontSize="170" fill="#064E3B"
          textAnchor="middle" fontStyle="italic" letterSpacing="-4"
        >XXL</text>
        <text
          className="xxl-front"
          x="340" y="265"
          fontFamily="Rubik, Arial, sans-serif"
          fontWeight="900" fontSize="170" fill="#059669"
          textAnchor="middle" fontStyle="italic" letterSpacing="-4"
        >XXL</text>

        {/* Flash overlay — hero only */}
        {isHero && (
          <rect
            className="xxl-flash"
            x="0" y="0" width="680" height="320"
            fill="#FFFFFF" opacity="0" pointerEvents="none"
          />
        )}

        {tagline}
      </g>
    </svg>
  );
}
