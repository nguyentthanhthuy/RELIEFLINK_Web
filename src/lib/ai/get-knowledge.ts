import { prisma } from "@/lib/prisma";

export async function getSystemKnowledge(userId: number) {
    // 1. Thông tin người dùng
    const user = await prisma.nguoi_dungs.findUnique({
        where: { id: userId },
    });

    // 2. Danh sách yêu cầu cứu trợ
    let requests;
    const requestSelect = {
        id: true,
        loai_yeu_cau: true,
        mo_ta: true,
        so_nguoi: true,
        trang_thai: true,
        created_at: true,
        ly_do_tu_choi: true,
        dia_chi: true,
        phan_phois: {
            select: {
                trang_thai: true,
                thoi_gian_giao: true,
                nguon_luc: {
                    select: { ten_nguon_luc: true, don_vi: true, so_luong: true }
                },
                tinh_nguyen_vien: {
                    select: { ho_va_ten: true, so_dien_thoai: true }
                }
            }
        }
    };

    if (user?.vai_tro === 'admin') {
        // Nếu là admin, lấy 15 yêu cầu mới nhất (đã tối ưu fields)
        requests = await prisma.yeu_cau_cuu_tros.findMany({
            orderBy: { created_at: 'desc' },
            take: 15,
            select: {
                ...requestSelect,
                nguoi_dung: { // Kèm thông tin người gửi yêu cầu
                    select: { ho_va_ten: true, so_dien_thoai: true }
                }
            }
        });
    } else {
        // Nếu là người dùng thường
        requests = await prisma.yeu_cau_cuu_tros.findMany({
            where: { id_nguoi_dung: userId },
            orderBy: { created_at: 'desc' },
            take: 20,
            select: requestSelect
        });
    }

    // 3. Thông báo gần đây nhất (tối ưu fields)
    const notifications = await prisma.thong_baos.findMany({
        where: { id_nguoi_nhan: userId },
        orderBy: { created_at: "desc" },
        take: 5,
        select: {
            tieu_de: true,
            noi_dung: true,
            loai_thong_bao: true,
            created_at: true
        }
    });

    // 4. Danh sách trung tâm cứu trợ (tối ưu fields)
    const centers = await prisma.trung_tam_cuu_tros.findMany({
        select: {
            ten_trung_tam: true,
            dia_chi: true,
            so_lien_he: true
        }
    });

    return `
===== DỮ LIỆU HỆ THỐNG RELIEFLINK =====

THÔNG TIN NGƯỜI DÙNG:
${JSON.stringify(user, null, 2)}

YÊU CẦU CỨU TRỢ CỦA NGƯỜI DÙNG:
${JSON.stringify(requests, null, 2)}

THÔNG BÁO GẦN ĐÂY:
${JSON.stringify(notifications, null, 2)}

DANH SÁCH TRUNG TÂM CỨU TRỢ:
${JSON.stringify(centers, null, 2)}
`;
}
