package com.nascon.app.data

/** Plain-language sentences for every error code the backend can return. Raw codes are never shown. */
object Messages {
    const val NETWORK = "Can't reach the server. Check your connection or the server address."

    private val map = mapOf(
        "UNAUTHORIZED" to "Your session has ended. Please sign in again.",
        "INVALID_CREDENTIALS" to "That email and password don't match.",
        "FORBIDDEN" to "Your account isn't allowed to do this.",
        "NOT_FOUND" to "We couldn't find that.",
        "RATE_LIMITED" to "Too many requests. Wait a few seconds and try again.",
        "VALIDATION_ERROR" to "Some details are missing or invalid. Check the form and try again.",
        "SERVER" to "Something went wrong on the server. Please try again.",
        "CROSS_TENANT_TRANSFER" to "Players can only move between clubs of the same organisation.",
        "DUPLICATE_EVENT_ID" to "This event was already recorded.",
        "DUPLICATE_ORDER_ID" to "This order was already placed.",
        "EVENT_NOT_FOUND" to "The event you tried to correct no longer exists.",
        "ILLEGAL_TRANSITION" to "That change isn't possible from the current status.",
        "INNINGS_COMPLETE" to "This innings is already complete.",
        "INVALID_BASE_VERSION" to "The match or player changed on the server before this was sent.",
        "INVALID_COMPENSATION" to "That event can't be corrected.",
        "INVALID_DISCOUNT_CODE" to "That discount code isn't valid.",
        "LEAGUE_NOT_FOUND" to "That league no longer exists.",
        "MATCH_NOT_FOUND" to "That match no longer exists.",
        "MATCH_NOT_IN_PROGRESS" to "The match isn't in progress. Start it first, or it has already ended.",
        "MIN_POSITION_VIOLATION" to "This move would leave the squad without a required position.",
        "NOT_IN_SQUAD" to "The player is no longer in this squad.",
        "ORDER_NOT_FOUND" to "We couldn't find that order.",
        "OUT_OF_STOCK" to "Sorry, that item is out of stock in the quantity you chose.",
        "PAYMENT_CAPTURE_FAILED" to "The payment was approved but couldn't be completed. You haven't been charged.",
        "PAYMENT_DECLINED" to "The card was declined. Try another test card.",
        "PLAYER_NOT_FOUND" to "That player no longer exists.",
        "PLAYER_ON_LOAN" to "The player is currently on loan and can't be moved.",
        "PRODUCT_NOT_FOUND" to "That product is no longer available.",
        "SQUAD_FULL" to "The destination squad is full.",
        "SQUAD_NOT_FOUND" to "The destination squad doesn't exist.",
        "TIE_NOT_ALLOWED" to "This match can't end level. Record a tie-break winner first.",
        "TRANSFER_WINDOW_CLOSED" to "The transfer window is closed on that date.",
        "UNKNOWN_EVENT_TYPE" to "That event type isn't allowed for this sport.",
        "VARIANT_NOT_FOUND" to "That size or option is no longer available.",
        "SERIES_ALREADY_DECIDED" to "This series is already decided.",
    )

    fun forCode(code: String?): String = map[code] ?: "Something went wrong. Please try again."

    /** "three_pointer" -> "Three pointer". Labels come from server ids, so any sport works. */
    fun label(id: String?): String {
        if (id.isNullOrBlank()) return ""
        val s = id.replace('_', ' ').replace('-', ' ').trim()
        return s.replaceFirstChar { it.uppercase() }
    }
}
