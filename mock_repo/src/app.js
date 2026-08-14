const express = require('express');
const app = express();
app.use(express.json());

// Routes
app.post('/api/bookings', (req, res) => {
    res.json({ message: "Booking endpoint" });
});

module.exports = app;