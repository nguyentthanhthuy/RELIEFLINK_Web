"use client";

import { useState } from "react";
import { useAuthStore } from "@/store/authStore";

export default function ChatBox() {
    const [open, setOpen] = useState(false);
    const [messages, setMessages] = useState<{ sender: string; text: string }[]>([]);
    const [input, setInput] = useState("");
    const { user } = useAuthStore();

    const sendMessage = async (queryType?: string) => {
        if (!input.trim()) return;

        if (!user) {
            setMessages(prev => [...prev, { sender: "bot", text: "Vui lòng đăng nhập để sử dụng tính năng này." }]);
            return;
        }

        const userMsg = { sender: "user", text: input };
        setMessages(prev => [...prev, userMsg]);

        try {
            const bodyPayload: any = { message: input, userId: user.id };
            if (queryType) bodyPayload.queryType = queryType;

            const res = await fetch("/api/chat", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(bodyPayload)
            });

            const data = await res.json();
            // If API returned structured data, render it specially
            if (data.data && data.type) {
                // Create a simple textual rendering for arrays/objects
                let text = "";
                try {
                    if (Array.isArray(data.data)) {
                        text = data.data.slice(0, 10).map((item: any, idx: number) => `${idx + 1}. ${JSON.stringify(item)}`).join('\n');
                    } else if (typeof data.data === 'object') {
                        text = JSON.stringify(data.data, null, 2);
                    } else {
                        text = String(data.data);
                    }
                } catch (e) {
                    text = String(data.data);
                }

                setMessages(prev => [...prev, { sender: "bot", text: text }]);
            } else {
                const botText = data.reply ?? "No response";
                setMessages(prev => [...prev, { sender: "bot", text: botText }]);
            }
        } catch (error) {
            console.error("Chat error:", error);
            setMessages(prev => [...prev, { sender: "bot", text: "Có lỗi xảy ra, vui lòng thử lại sau." }]);
        }
        
        setInput("");
    };


    return (
        <div className="fixed bottom-6 right-6 z-50">
            {/* Icon mở chat */}
            {!open && (
                <button
                    onClick={() => setOpen(true)}
                    className="w-16 h-16 rounded-full shadow-2xl bg-green-600 flex items-center justify-center hover:scale-110 transition-all duration-300"
                >
                    <svg width="30" height="30" fill="white" viewBox="0 0 24 24">
                        <path d="M20 2H4C2.9 2 2 2.9 2 4V22L6 18H20C21.1 18 22 17.1 22 16V4C22 2.9 21.1 2 20 2Z" />
                    </svg>
                </button>
            )}

            {open && (
                <div className="w-80 bg-white rounded-2xl shadow-2xl border p-3 flex flex-col animate-[fadeIn_0.25s_ease-out] ">
                    {/* Animation keyframes */}
                    <style jsx>{`
                        @keyframes fadeIn {
                            from { opacity: 0; transform: scale(0.8); }
                            to { opacity: 1; transform: scale(1); }
                        }
                    `}</style>

                    {/* Header */}
                    <div className="flex justify-between items-center pb-2 border-b">
                        <h4 className="font-bold text-lg text-green-600">Relief Chat</h4>
                        <button
                            onClick={() => setOpen(false)}
                            className="text-gray-600 hover:text-red-500 text-xl transition"
                        >
                            ✕
                        </button>
                    </div>

                    {/* Quick query buttons */}
                    <div className="flex gap-2 py-2">
                        <button
                            onClick={async () => {
                                // Request user's own requests
                                await sendMessage('user_requests');
                            }}
                            className="text-xs px-2 py-1 bg-gray-100 rounded-full"
                        >
                            Yêu cầu của tôi
                        </button>
                        <button
                            onClick={async () => { await sendMessage('notifications'); }}
                            className="text-xs px-2 py-1 bg-gray-100 rounded-full"
                        >
                            Thông báo
                        </button>
                        <button
                            onClick={async () => { await sendMessage('centers'); }}
                            className="text-xs px-2 py-1 bg-gray-100 rounded-full"
                        >
                            Trung tâm cứu trợ
                        </button>
                    </div>

                    {/* Messages */}
                    <div className="h-72 overflow-y-auto p-2 space-y-2">
                        {messages.map((m, i) => (
                            <div
                                key={i}
                                className={`
                                    px-3 py-2 rounded-xl max-w-[75%] text-sm shadow
                                    ${
                                        m.sender === "user"
                                            ? "bg-green-600 text-white ml-auto rounded-br-none"
                                            : "bg-gray-200 text-black mr-auto rounded-bl-none"
                                    }
                                `}
                            >
                                {m.text}
                            </div>
                        ))}
                    </div>

                    {/* Input */}
                    <div className="flex gap-2 mt-2">
                        <input
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && sendMessage()}
                            placeholder="Nhập tin nhắn..."
                            className="flex-1 px-3 py-2 border rounded-full bg-gray-50 focus:ring focus:ring-green-200 outline-none"
                        />
                        <button
                            onClick={sendMessage}
                            className="bg-green-600 text-white px-4 py-2 rounded-full hover:bg-green-700 transition shadow"
                        >
                            Gửi
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}
