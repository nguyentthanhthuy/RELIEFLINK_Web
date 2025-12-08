import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { getSystemKnowledge } from "@/lib/ai/get-knowledge";

export async function POST(req: Request) {
    try {
        const body = await req.json();
        const { message, userId, queryType } = body;

        if (!userId) {
            return NextResponse.json(
                { error: "Missing userId" },
                { status: 400 }
            );
        }

        const apiKey = process.env.GROQ_API_KEY;
        if (!apiKey) {
            return NextResponse.json(
                { error: "Missing GROQ_API_KEY" },
                { status: 500 }
            );
        }

        // Nếu client gửi queryType, trả về dữ liệu hệ thống tương ứng (không gọi Groq)
        if (queryType) {
            if (!userId) {
                return NextResponse.json({ error: "Missing userId for query" }, { status: 400 });
            }

            switch (queryType) {
                case 'user_requests': {
                    const requests = await prisma.yeu_cau_cuu_tros.findMany({
                        where: { id_nguoi_dung: userId },
                        orderBy: { created_at: 'desc' },
                        take: 50,
                        select: {
                            id: true,
                            loai_yeu_cau: true,
                            mo_ta: true,
                            so_nguoi: true,
                            trang_thai: true,
                            created_at: true,
                            dia_chi: true
                        }
                    });
                    return NextResponse.json({ type: 'user_requests', data: requests });
                }
                case 'notifications': {
                    const notifications = await prisma.thong_baos.findMany({
                        where: { id_nguoi_nhan: userId },
                        orderBy: { created_at: 'desc' },
                        take: 20,
                        select: {
                            tieu_de: true,
                            noi_dung: true,
                            loai_thong_bao: true,
                            created_at: true
                        }
                    });
                    return NextResponse.json({ type: 'notifications', data: notifications });
                }
                case 'centers': {
                    const centers = await prisma.trung_tam_cuu_tros.findMany({
                        select: {
                            id: true,
                            ten_trung_tam: true,
                            dia_chi: true,
                            so_lien_he: true
                        },
                        take: 50
                    });
                    return NextResponse.json({ type: 'centers', data: centers });
                }
                case 'summary': {
                    // Example summary: counts
                    const [reqCount, notifCount, centerCount] = await Promise.all([
                        prisma.yeu_cau_cuu_tros.count({ where: { id_nguoi_dung: userId } }),
                        prisma.thong_baos.count({ where: { id_nguoi_nhan: userId } }),
                        prisma.trung_tam_cuu_tros.count()
                    ]);
                    return NextResponse.json({ type: 'summary', data: { reqCount, notifCount, centerCount } });
                }
                default:
                    return NextResponse.json({ error: 'Unknown queryType' }, { status: 400 });
            }
        }

        // LẤY DỮ LIỆU HỆ THỐNG RELIEFLINK để kèm khi gửi cho Groq
        console.log("Fetching knowledge for user:", userId);
        const knowledge = await getSystemKnowledge(userId);
        console.log("Knowledge retrieved length:", knowledge.length);

        // Gửi lên GROQ
        console.log("Sending request to Groq...");
        const response = await fetch("https://api.groq.com/openai/v1/chat/completions", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${apiKey}`,
            },
            body: JSON.stringify({
                model: "llama-3.3-70b-versatile",
                messages: [
                    {
                        role: "system",
                        content: `
Bạn là trợ lý AI thông minh của hệ thống RELIEFLINK - Nền tảng cứu trợ thiên tai.
Nhiệm vụ của bạn là hỗ trợ người dùng dựa trên thông tin được cung cấp.

DỮ LIỆU HỆ THỐNG VÀ NGƯỜI DÙNG HIỆN TẠI:
${knowledge}

HƯỚNG DẪN TRẢ LỜI:
1. Sử dụng dữ liệu trên để trả lời các câu hỏi cụ thể về trạng thái, yêu cầu, hoặc thông tin cứu trợ.
2. Nếu người dùng hỏi câu hỏi chung (chào hỏi, chức năng hệ thống...), hãy trả lời thân thiện và tự nhiên như một trợ lý ảo.
3. Nếu người dùng hỏi về thông tin cá nhân/cụ thể mà KHÔNG có trong dữ liệu được cung cấp, hãy lịch sự báo là không tìm thấy thông tin đó trong hệ thống.
4. Trả lời ngắn gọn, súc tích, bằng tiếng Việt.
                        `
                    },
                    {
                        role: "user",
                        content: message
                    }
                ],
                temperature: 0.2,
            }),
        });

        const data = await response.json();

        if (!response.ok) {
            console.error("Groq API Error:", data);
            return NextResponse.json(
                { reply: `Lỗi kết nối AI: ${data?.error?.message || "Unknown error"}` },
                { status: 200 } // Return 200 so frontend displays the message
            );
        }

        const reply =
            data?.choices?.[0]?.message?.content ??
            "Xin lỗi, tôi chưa tìm thấy dữ liệu phù hợp (Empty response).";

        return NextResponse.json({ reply });

    } catch (error) {
        console.error("CHAT API ERROR:", error);
        return NextResponse.json(
            { error: "Server error" },
            { status: 500 }
        );
    }
}
