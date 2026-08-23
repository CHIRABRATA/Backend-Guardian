// Simulated Concurrency Test Suite
const { bookSeat } = require('../src/services/booking.service');

// Mock Database with in-memory seat state
global.db = {
    seat: { id: 1, show_id: 101, seat_number: "A1", is_booked: false, user_id: null },
    async query(sql, params) {
        // Handle atomic UPDATE simulation
        if (sql.includes("UPDATE") && sql.includes("WHERE")) {
            if (!this.seat.is_booked) {
                this.seat.is_booked = true;
                this.seat.user_id = params[0] || params[2];
                return { rowCount: 1, affectedRows: 1 };
            }
            return { rowCount: 0, affectedRows: 0 };
        }

        // Handle SELECT query
        if (sql.includes("SELECT")) {
            return { rows: [ { ...this.seat } ] };
        }

        return { rows: [] };
    }
};

async function runConcurrencyTest() {
    console.log("▶ Running Concurrency Test: 2 simultaneous booking requests for Seat A1...");

    let successfulBookings = 0;
    let failedBookings = 0;

    const request1 = bookSeat(101, "A1", "user_1")
        .then(() => successfulBookings++)
        .catch(() => failedBookings++);

    const request2 = bookSeat(101, "A1", "user_2")
        .then(() => successfulBookings++)
        .catch(() => failedBookings++);

    await Promise.all([request1, request2]);

    if (successfulBookings === 1 && failedBookings === 1) {
        console.log("✅ TEST PASSED: Exactly 1 user booked the seat. Race condition prevented!");
        process.exit(0);
    } else {
        console.error(`❌ TEST FAILED: Overbooking occurred! Successes: ${successfulBookings}, Failures: ${failedBookings}`);
        process.exit(1);
    }
}

runConcurrencyTest();