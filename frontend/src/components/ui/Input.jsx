export default function Input({
    label,
    type = "text",
    value,
    onChange,
    placeholder = "",
    error = "",
    disabled = false
}) {
    return(
        <div className="flex flex-col gap-1">
            {label && (
                <label className="text-sm font-medium text-grey-700">{label}</label>
            )}
            <input
                type={type}
                value={value}
                onChange={onChange}
                placeholder={placeholder}
                disabled={disabled}
                className={`
                    px-3 py-2 border rounded-lg text-sm outline-none transition
                    focus:ring-2 focus:ring-blue-500
                    disabled:bg-gray-100 disabled:cursor-not-allowed
                    ${error ? "border-red-500" : "border-gray-300"} 
                `}
            ></input>
            {error && <p className="text-xs text-red-500">{error}</p>}
        </div>
    );
}