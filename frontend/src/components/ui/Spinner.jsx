export default function Spinner({ size = "md" }) {
  const sizes = {
    sm: "w-4 h-4",
    md: "w-6 h-6",
    lg: "w-10 h-10",
  };

  return (
    <div
      className={`${sizes[size]} rounded-full border-2 border-gray-300 border-t-blue-600`}
      style={{ animation: "spin 0.75s linear infinite" }}
    />
  );
}