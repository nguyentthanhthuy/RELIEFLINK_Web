"use client";

import { useState, useRef, useEffect } from "react";
import { MessageSquare, X, Send, User, Bot, Loader2 } from "lucide-react";
import { useAuthStore } from "@/store/authStore";

interface Message {
    text: string;
    sender: "user" | "bot";
    timestamp: Date;
}

export default function RasaChatWidget() {
    const [isOpen, setIsOpen] = useState(false);
    const [messages, setMessages] = useState<Message[]>([
        {
            text: "Xin chào! Tôi là trợ lý ảo ReliefLink (Hybrid). Tôi có thể giúp bạn trả lời các câu hỏi về thiên tai, dự báo, hoặc kiến thức chung.",
            sender: "bot",
            timestamp: new Date(),
        },
    ]);
    const [inputText, setInputText] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    // Use API proxy instead of direct localhost (which doesn't work from browser)
    const RASA_API_URL = "/api/rasa";
    // Fallback to Next.js API (which calls Groq/OpenAI/etc)
    const FALLBACK_API_URL = "/api/chat";
    const { user } = useAuthStore();

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages, isOpen]);

    const handleSendMessage = async () => {
        if (!inputText.trim()) return;

        const userMessage = inputText;
        setInputText("");

        // Add user message
        setMessages((prev) => [
            ...prev,
            { text: userMessage, sender: "user", timestamp: new Date() },
        ]);
        setIsLoading(true);

        try {
            // --- PHA 1: Thử hỏi Rasa trước ---
            let handledByRasa = false;
            try {
                const rasaResponse = await fetch(RASA_API_URL, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        sender: "user-" + Math.random().toString(36).substr(2, 9),
                        message: userMessage,
                    }),
                });

                if (rasaResponse.ok) {
                    const data = await rasaResponse.json();
                    // Logic: Rasa trả lời có nội dung và không phải là câu fallback mặc định
                    if (Array.isArray(data) && data.length > 0) {
                        // Check if it's not a generic fallback asking for clarification
                        const isGenericFallback = data.some((msg: any) =>
                            msg.text && (msg.text.includes("I didn't quite understand") || msg.text.includes("xin lỗi, tôi chưa hiểu"))
                        );

                        if (!isGenericFallback) {
                            data.forEach((msg: any) => {
                                setMessages((prev) => [
                                    ...prev,
                                    { text: msg.text || "Bot sent an image/action.", sender: "bot", timestamp: new Date() },
                                ]);
                            });
                            handledByRasa = true;
                        }
                    }
                }
            } catch (rasaError) {
                console.warn("Rasa unavailable, skipping to fallback...", rasaError);
            }

            // --- PHA 2: Nếu Rasa bó tay, hỏi AI "xịn" (Groq/LLM) ---
            if (!handledByRasa) {
                try {
                    const fallbackResponse = await fetch(FALLBACK_API_URL, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ message: userMessage, userId: user?.id }),
                    });

                    if (fallbackResponse.ok) {
                        const data = await fallbackResponse.json();
                        // Adjust according to your real API response
                        const botReply = data.reply || data.message || data.response || "Xin lỗi, tôi không thể trả lời lúc này.";

                        setMessages((prev) => [
                            ...prev,
                            { text: botReply, sender: "bot", timestamp: new Date() },
                        ]);
                    } else {
                        throw new Error("Fallback API Error");
                    }
                } catch (fallbackError) {
                    console.error("Fallback AI failed:", fallbackError);
                    setMessages((prev) => [
                        ...prev,
                        {
                            text: "⚠️ Hiện tại cả Rasa Bot và AI System đều đang bận hoặc quá tải. Vui lòng thử lại sau ít phút.",
                            sender: "bot",
                            timestamp: new Date()
                        },
                    ]);
                }
            }

        } catch (error) {
            console.error("Critical Chat Error:", error);
        } finally {
            setIsLoading(false);
        }
    };

    const handleKeyPress = (e: React.KeyboardEvent) => {
        if (e.key === "Enter") {
            handleSendMessage();
        }
    };

    return (
        <div className="fixed bottom-6 right-6 z-[9999] font-sans">
            {!isOpen && (
                <button
                    onClick={() => setIsOpen(true)}
                    className="flex h-14 w-14 items-center justify-center rounded-full bg-blue-600 text-white shadow-lg transition-transform hover:scale-110 hover:bg-blue-700"
                >
                    <MessageSquare size={28} />
                </button>
            )}

            {isOpen && (
                <div className="flex h-[500px] w-[350px] flex-col rounded-2xl border border-gray-200 bg-white shadow-2xl dark:border-gray-700 dark:bg-gray-900 sm:w-[400px]">
                    <div className="flex items-center justify-between rounded-t-2xl bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-3 text-white">
                        <div className="flex items-center gap-2">
                            <div className="rounded-full bg-white/20 p-1">
                                <Bot size={20} className="text-white" />
                            </div>
                            <div>
                                <h3 className="text-sm font-bold">ReliefLink Hybrid Bot</h3>
                                <span className="flex items-center gap-1 text-[10px] text-blue-100 opacity-90">
                                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-green-400"></span>
                                    Rasa + Groq AI
                                </span>
                            </div>
                        </div>
                        <button
                            onClick={() => setIsOpen(false)}
                            className="rounded-full p-1 transition-colors hover:bg-white/20"
                        >
                            <X size={20} />
                        </button>
                    </div>

                    <div className="flex-1 overflow-y-auto bg-gray-50 p-4 dark:bg-gray-800">
                        <div className="flex flex-col gap-3">
                            {messages.map((msg, index) => (
                                <div
                                    key={index}
                                    className={`flex items-start gap-2 ${msg.sender === "user" ? "flex-row-reverse" : "flex-row"
                                        }`}
                                >
                                    <div
                                        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${msg.sender === "user"
                                            ? "bg-blue-600 text-white"
                                            : "bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-300"
                                            }`}
                                    >
                                        {msg.sender === "user" ? <User size={16} /> : <Bot size={16} />}
                                    </div>
                                    <div
                                        className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm shadow-sm ${msg.sender === "user"
                                            ? "bg-blue-600 text-white"
                                            : "bg-white text-gray-800 dark:bg-gray-700 dark:text-gray-100"
                                            }`}
                                    >
                                        <p className="whitespace-pre-wrap leading-relaxed">{msg.text}</p>
                                        <span className="mt-1 block text-[10px] opacity-70">
                                            {msg.timestamp.toLocaleTimeString([], {
                                                hour: "2-digit",
                                                minute: "2-digit",
                                            })}
                                        </span>
                                    </div>
                                </div>
                            ))}
                            {isLoading && (
                                <div className="flex items-start gap-2">
                                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gray-200 dark:bg-gray-700">
                                        <Bot size={16} />
                                    </div>
                                    <div className="rounded-2xl bg-white px-4 py-2 shadow-sm dark:bg-gray-700">
                                        <div className="flex items-center gap-2">
                                            <span className="text-xs text-gray-500">Đang suy nghĩ...</span>
                                            <Loader2 size={14} className="animate-spin text-blue-600" />
                                        </div>
                                    </div>
                                </div>
                            )}
                            <div ref={messagesEndRef} />
                        </div>
                    </div>

                    <div className="border-t border-gray-100 bg-white p-3 dark:border-gray-700 dark:bg-gray-900">
                        <div className="flex items-center gap-2 rounded-full border border-gray-200 bg-gray-50 px-4 py-2 focus-within:border-blue-500 focus-within:ring-1 focus-within:ring-blue-500/20 dark:border-gray-700 dark:bg-gray-800">
                            <input
                                type="text"
                                value={inputText}
                                onChange={(e) => setInputText(e.target.value)}
                                onKeyDown={handleKeyPress}
                                placeholder="Hỏi về cứu trợ hoặc thời tiết..."
                                className="flex-1 bg-transparent text-sm outline-none dark:text-white"
                                disabled={isLoading}
                            />
                            <button
                                onClick={handleSendMessage}
                                disabled={!inputText.trim() || isLoading}
                                className="text-blue-600 transition-colors hover:text-blue-700 disabled:opacity-50 dark:text-blue-400"
                            >
                                <Send size={20} />
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
