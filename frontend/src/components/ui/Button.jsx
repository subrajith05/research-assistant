const variants = {
  primary: "bg-blue-600 hover:bg-blue-700 text-white",
  secondary: "bg-gray-200 hover:bg-gray-300 text-gray-800",
  danger: "bg-red-500 hover:bg-red-600 text-white",
};

export default function Button({
    label,
    onClick,
    type = "button",
    variant = "primary",
    disabled = false,
    loading = false,
    fullWidth = false,
}) {
    return(
        <button
            type={type}
            onClick={onClick}
            disabled={disabled || loading}
            className={`
            px-4 py-2 rounded-lg font-medium text-sm transition-colors duration-150
            ${variants[variant]}
            ${fullWidth ? "w-full" : ""}
            ${disabled || loading ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}
            `}
        >
        {loading ? "Loading..." : label}
        </button>
    );
}