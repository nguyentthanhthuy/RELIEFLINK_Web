const { PrismaClient } = require('@prisma/client');
const prisma = new PrismaClient();

async function main() {
    try {
        const centers = await prisma.trung_tam_cuu_tros.findMany();
        console.log(`Found ${centers.length} centers.`);
        if (centers.length === 0) {
            console.log("Database is empty. Please run 'yarn prisma:seed'");
        } else {
            console.log("First center:", centers[0].ten_trung_tam);
        }
    } catch (e) {
        console.error("Database connection error:", e);
    } finally {
        await prisma.$disconnect();
    }
}

main();
