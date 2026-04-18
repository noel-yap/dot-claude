# Shell Command Rules
- Always quote paths and directory names with double quotes: `cd "path/with unicode"`.
- Preserve Unicode characters exactly as-is; never transliterate or escape them.
- For paths with spaces, Unicode, or special chars: use `"$PWD/my dir café 🎉"`.
- Examples:
    - Good: `ls "📁 dir"`
    - Bad: `ls 📁 dir` or `ls dir-with-café`