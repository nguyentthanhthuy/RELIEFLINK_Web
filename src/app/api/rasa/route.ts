import { NextResponse } from "next/server";

const RASA_URL = process.env.RASA_URL || "http://localhost:5005";

export async function POST(req: Request) {
    try {
        const body = await req.json();
        const { sender, message } = body;

        if (!message) {
            return NextResponse.json(
                { error: "Missing message" },
                { status: 400 }
            );
        }

        console.log("Proxying to Rasa:", { sender, message });

        const rasaResponse = await fetch(`${RASA_URL}/webhooks/rest/webhook`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                sender: sender || `user-${Date.now()}`,
                message: message,
            }),
        });

        if (!rasaResponse.ok) {
            const errorText = await rasaResponse.text();
            console.error("Rasa error:", errorText);
            return NextResponse.json(
                { error: "Rasa server error", details: errorText },
                { status: rasaResponse.status }
            );
        }

        const data = await rasaResponse.json();
        console.log("Rasa response:", data);

        return NextResponse.json(data);
    } catch (error) {
        console.error("Rasa proxy error:", error);
        return NextResponse.json(
            { error: "Failed to connect to Rasa server" },
            { status: 503 }
        );
    }
}

// Health check endpoint
export async function GET() {
    try {
        const response = await fetch(RASA_URL);
        if (response.ok) {
            const text = await response.text();
            return NextResponse.json({ status: "ok", rasa: text });
        }
        return NextResponse.json({ status: "error", message: "Rasa not responding" }, { status: 503 });
    } catch {
        return NextResponse.json({ status: "error", message: "Rasa server unavailable" }, { status: 503 });
    }
}
