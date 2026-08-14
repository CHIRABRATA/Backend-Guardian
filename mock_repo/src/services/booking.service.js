// Simulated buggy booking service with race condition
async function bookSeat(showId, seatNumber, userId) {
    const seat = await db.query(
        "SELECT * FROM seats WHERE show_id = $1 AND seat_number = $2",
        [showId, seatNumber]
    );

    if (seat.rows[0].is_booked) {
        throw new Error("Seat already booked");
    }

    // Bug: Missing transaction and lock, race condition occurs here
    await db.query(
        "UPDATE seats SET is_booked = true, user_id = $3 WHERE show_id = $1 AND seat_number = $2",
        [showId, seatNumber, userId]
    );

    return { success: true };
}