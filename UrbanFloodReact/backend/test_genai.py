import google.generativeai as genai

def test_backend_func(a: int) -> int:
    "a test backend func"
    return a + 1

frontend_tool = genai.protos.Tool(
    function_declarations=[
        genai.protos.FunctionDeclaration(
            name="test_frontend",
            description="a test frontend func"
        )
    ]
)

try:
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        tools=[test_backend_func, frontend_tool]
    )
    print("SUCCESS")
except Exception as e:
    print(f"FAILED: {e}")
