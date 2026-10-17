package com.nascon.app.ui

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

@Composable fun MatchScreen(id: String) = Page("Match", back = true) { Text(id) }
@Composable fun ClubTab() = Page("Club") { }
@Composable fun ClubScreen(id: String, back: Boolean) = Page("Club", back = back) { Text(id) }
@Composable fun StoreScreen() = Page("Store") { }
@Composable fun ProductScreen(id: String) = Page("Product", back = true) { Text(id) }
@Composable fun CartScreen() = Page("Cart", back = true) { }
@Composable fun ReceiptScreen(id: String) = Page("Receipt", back = true) { Text(id) }
@Composable fun OrdersScreen() = Page("Orders", back = true) { }
