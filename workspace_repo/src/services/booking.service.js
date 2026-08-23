// Fixed booking service with atomic concurrency protection
async function bookSeat(showId, seatNumber, userId) {
    const result = await db.query(
        "UPDATE seats SET is_booked = true, user_id = $3 WHERE show_id = $1 AND seat_number = $2 AND is_booked = false",
        [showId, seatNumber, userId]
    );

    if (!result || (result.rowCount === 0 && result.affectedRows === 0)) {
        throw new Error("Seat already booked");
    }

    return { success: true };
}

module.exports = { bookSeat };
