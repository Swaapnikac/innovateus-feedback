"use client";

interface SliderQuestionProps {
  value: string;
  onChange: (value: string) => void;
  min?: number;
  max?: number;
  step?: number;
  labels?: { low?: string; high?: string };
}

export function SliderQuestion({
  value,
  onChange,
  min = 0,
  max = 100,
  step = 1,
  labels,
}: SliderQuestionProps) {
  const current = value === "" ? (min + max) / 2 : Number(value);
  const isSet = value !== "";

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-xs text-brand-blue/50">{labels?.low ?? min}</span>
        <div
          className={`px-4 py-1.5 rounded-full text-sm font-semibold ${
            isSet ? "bg-brand-blue text-white" : "bg-brand-light-blue text-brand-blue/40"
          }`}
        >
          {isSet ? current : "—"}
        </div>
        <span className="text-xs text-brand-blue/50">{labels?.high ?? max}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={current}
        onChange={(e) => onChange(e.target.value)}
        className="w-full h-2 bg-brand-blue/10 rounded-full appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-5 [&::-webkit-slider-thumb]:h-5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-brand-blue [&::-webkit-slider-thumb]:cursor-pointer [&::-webkit-slider-thumb]:shadow-md"
      />
    </div>
  );
}
