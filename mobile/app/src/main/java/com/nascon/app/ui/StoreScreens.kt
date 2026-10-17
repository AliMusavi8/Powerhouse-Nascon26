package com.nascon.app.ui

import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.os.Build
import android.provider.MediaStore
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ReceiptLong
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.OpenInNew
import androidx.compose.material.icons.filled.Remove
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Share
import androidx.compose.material.icons.filled.ShoppingBag
import androidx.compose.material.icons.filled.ShoppingCart
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.Badge
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import com.nascon.app.CartLine
import com.nascon.app.data.ApiError
import com.nascon.app.data.Messages
import com.nascon.app.data.SyncManager
import com.nascon.app.data.arr
import com.nascon.app.data.int
import com.nascon.app.data.jobj
import com.nascon.app.data.long
import com.nascon.app.data.money
import com.nascon.app.data.obj
import com.nascon.app.data.str
import com.nascon.app.graph
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import java.io.File

/** Last checkout responses, so the receipt opens instantly after paying. */
val receipts = mutableStateMapOf<String, JsonObject>()

@Composable
private fun CartAction() {
    val g = graph()
    val ui = LocalUi.current
    val n = g.cart.sumOf { it.quantity }
    IconButton(onClick = { ui.nav.navigate("cart") { launchSingleTop = true } }) {
        BadgedBox(badge = { if (n > 0) Badge { Text("$n") } }) {
            Icon(Icons.Filled.ShoppingCart, contentDescription = if (n > 0) "Cart, $n items" else "Cart, empty")
        }
    }
}

private fun attrText(v: JsonObject): String =
    v.obj("attributes")?.entries?.joinToString(" · ") { (k, value) -> "${Messages.label(k)}: ${(value as? JsonPrimitive)?.content ?: value}" } ?: ""

private fun attrShort(v: JsonObject): String =
    v.obj("attributes")?.values?.joinToString(" / ") { (it as? JsonPrimitive)?.content ?: it.toString() }?.ifBlank { null } ?: "Standard"

@Composable
fun StoreScreen() {
    val ui = LocalUi.current
    val res = rememberRes("/api/v1/products")
    Page("Store", savedAt = res.loaded?.savedAt, actions = { CartAction() }) {
        ResBox(res) { l ->
            val products = l.data.arr("products")
            if (products.isEmpty()) {
                Empty(Icons.Filled.ShoppingBag, "No products yet", "The club store is empty right now."); return@ResBox
            }
            LazyColumn(Modifier.fillMaxSize()) {
                products.groupBy { Messages.label(it.str("category") ?: "Other") }.forEach { (cat, list) ->
                    item(key = "c$cat") { SectionLabel(cat) }
                    items(list, key = { it.str("product_id") ?: "" }) { p ->
                        val vs = p.arr("variants")
                        val min = vs.mapNotNull { it.long("price_minor") }.minOrNull()
                        val inStock = vs.any { (it.int("stock") ?: 0) > 0 }
                        Row(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface)
                            .clickable(onClickLabel = "Open product") { ui.nav.navigate("product/${p.str("product_id")}") }
                            .padding(horizontal = 16.dp, vertical = 10.dp),
                            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            Box(Modifier.size(56.dp).clip(RoundedCornerShape(8.dp)).background(MaterialTheme.colorScheme.surfaceVariant), contentAlignment = Alignment.Center) {
                                Icon(Icons.Filled.ShoppingBag, null, tint = extra.muted)
                            }
                            Column(Modifier.weight(1f)) {
                                Text(p.str("name") ?: "", fontWeight = FontWeight.Medium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                Text((if (vs.size > 1) "From " else "") + money(min, vs.firstOrNull()?.str("currency")), style = NumStyle, color = extra.muted)
                            }
                            if (!inStock) Chip("Sold out", extra.bad, extra.badBg)
                        }
                        Divider()
                    }
                }
                item { Box(Modifier.height(24.dp)) }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ProductScreen(productId: String) {
    val g = graph()
    val ui = LocalUi.current
    val res = rememberRes("/api/v1/products")
    val p = res.loaded?.data?.arr("products")?.firstOrNull { it.str("product_id") == productId }
    var selected by remember { mutableStateOf<String?>(null) }
    var qty by remember { mutableStateOf(1) }
    Page(p?.str("name") ?: "Product", back = true, savedAt = res.loaded?.savedAt, actions = { CartAction() }) {
        ResBox(res) { _ ->
            if (p == null) { Empty(Icons.Filled.ShoppingBag, "Product not found", "It may have been removed from the store."); return@ResBox }
            val vs = p.arr("variants")
            val v = vs.firstOrNull { it.str("variant_id") == selected } ?: vs.firstOrNull { (it.int("stock") ?: 0) > 0 }?.also { selected = it.str("variant_id") }
            val stock = v?.int("stock") ?: 0
            Column(Modifier.fillMaxSize()) {
                Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
                    Box(Modifier.fillMaxWidth().aspectRatio(2f).background(MaterialTheme.colorScheme.surfaceVariant), contentAlignment = Alignment.Center) {
                        Icon(Icons.Filled.ShoppingBag, contentDescription = null, tint = extra.muted, modifier = Modifier.size(64.dp))
                    }
                    Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface).padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(p.str("name") ?: "", style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
                            Text(money(v?.long("price_minor"), v?.str("currency")), style = NumStyle, fontSize = 18.sp, fontWeight = FontWeight.Bold)
                        }
                        p.str("description")?.let { Text(it, color = extra.muted) }
                        if (vs.size > 1 || vs.firstOrNull()?.obj("attributes")?.isNotEmpty() == true) {
                            Text("Options", style = MaterialTheme.typography.labelSmall, color = extra.muted)
                            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                vs.forEach { o ->
                                    val out = (o.int("stock") ?: 0) <= 0
                                    FilterChip(
                                        selected = o.str("variant_id") == v?.str("variant_id"),
                                        onClick = { if (!out) { selected = o.str("variant_id"); qty = 1 } },
                                        enabled = !out,
                                        label = { Text(attrShort(o) + if (out) " · sold out" else "", textDecoration = if (out) TextDecoration.LineThrough else null) },
                                        modifier = Modifier.heightIn(min = 48.dp).semantics { if (out) contentDescription = "${attrShort(o)}, sold out" },
                                    )
                                }
                            }
                        }
                        v?.let { Text(attrText(it), fontSize = 12.sp, color = extra.muted) }
                        Text(if (stock > 0) "$stock in stock" else "Sold out", fontSize = 13.sp, color = if (stock > 0) extra.ok else extra.bad)
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text("Quantity", Modifier.weight(1f))
                            IconButton(onClick = { if (qty > 1) qty-- }, enabled = qty > 1) { Icon(Icons.Filled.Remove, "Decrease quantity") }
                            Text("$qty", style = NumStyle, fontSize = 18.sp)
                            IconButton(onClick = { if (qty < stock) qty++ }, enabled = qty < stock) { Icon(Icons.Filled.Add, "Increase quantity") }
                        }
                    }
                }
                Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface)) {
                    Divider()
                    Button(
                        onClick = {
                            val vv = v ?: return@Button
                            val i = g.cart.indexOfFirst { it.variant.str("variant_id") == vv.str("variant_id") }
                            if (i >= 0) g.cart[i] = g.cart[i].copy(quantity = minOf(stock, g.cart[i].quantity + qty)) else g.cart.add(CartLine(p, vv, qty))
                            ui.toast("Added to cart.")
                        },
                        enabled = v != null && stock > 0,
                        modifier = Modifier.fillMaxWidth().padding(16.dp).heightIn(min = 52.dp),
                    ) { Text(if (stock > 0) "Add to cart · ${money((v?.long("price_minor") ?: 0) * qty, v?.str("currency"))}" else "Sold out") }
                }
            }
        }
    }
}

private val tokens = listOf(
    Triple("tok_success", "Test card: approved", "Payment goes through."),
    Triple("tok_declined", "Test card: declined", "The bank refuses the payment."),
    Triple("tok_capture_fail", "Test card: capture fails", "Approved, then fails to complete."),
)

@Composable
fun CartScreen() {
    val g = graph()
    val ui = LocalUi.current
    val scope = rememberCoroutineScope()
    var code by remember { mutableStateOf("") }
    var token by remember { mutableStateOf("tok_success") }
    var confirm by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val subtotal = g.cart.sumOf { (it.variant.long("price_minor") ?: 0) * it.quantity }
    val currency = g.cart.firstOrNull()?.variant?.str("currency")
    Page("Cart", back = true) {
        if (g.cart.isEmpty()) {
            Empty(Icons.Filled.ShoppingCart, "Your cart is empty", "Browse the store and add something you like.") {
                OutlinedButton(onClick = { ui.nav.navigate("store") }, modifier = Modifier.heightIn(min = 48.dp)) { Text("Go to store") }
            }
            return@Page
        }
        Column(Modifier.fillMaxSize()) {
            Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
                SectionLabel("Items")
                g.cart.toList().forEachIndexed { i, line ->
                    Row(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface).padding(start = 16.dp, top = 8.dp, bottom = 8.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(line.product.str("name") ?: "", fontWeight = FontWeight.Medium)
                            Text("${attrShort(line.variant)} · ${line.quantity} × ${money(line.variant.long("price_minor"), currency)}", fontSize = 12.sp, color = extra.muted)
                        }
                        Text(money((line.variant.long("price_minor") ?: 0) * line.quantity, currency), style = NumStyle)
                        IconButton(onClick = { g.cart.removeAt(i) }) { Icon(Icons.Outlined.Delete, "Remove ${line.product.str("name")}") }
                    }
                    Divider()
                }
                SectionLabel("Discount")
                Box(Modifier.background(MaterialTheme.colorScheme.surface).padding(16.dp)) {
                    OutlinedTextField(code, { code = it.uppercase().trim() }, label = { Text("Discount code (optional)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                }
                SectionLabel("Payment (test mode)")
                Column(Modifier.background(MaterialTheme.colorScheme.surface)) {
                    tokens.forEach { (t, label, hint) ->
                        Row(Modifier.fillMaxWidth().selectable(token == t, role = Role.RadioButton) { token = t }.heightIn(min = 56.dp).padding(horizontal = 16.dp),
                            verticalAlignment = Alignment.CenterVertically) {
                            RadioButton(selected = token == t, onClick = null)
                            Column(Modifier.padding(start = 12.dp)) { Text(label); Text(hint, fontSize = 12.sp, color = extra.muted) }
                        }
                    }
                }
                error?.let {
                    Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(16.dp))
                }
            }
            Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface).padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row { Text("Subtotal", Modifier.weight(1f), color = extra.muted); Text(money(subtotal, currency), style = NumStyle) }
                if (code.isNotBlank()) Text("Discount is applied at payment if the code is valid.", fontSize = 12.sp, color = extra.muted)
                Button(onClick = { confirm = true }, enabled = !busy, modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp)) {
                    Icon(Icons.Filled.Lock, null, modifier = Modifier.size(16.dp)); Text(if (busy) "  Paying…" else "  Pay ${money(subtotal, currency)}")
                }
            }
        }
    }
    if (confirm) Confirm("Place this order?", "You'll pay ${money(subtotal, currency)}${if (code.isNotBlank()) " before discount" else ""} with the selected test card.", "Pay",
        onDismiss = { confirm = false }) {
        confirm = false; busy = true; error = null
        scope.launch {
            try {
                val body = jobj(
                    "order_id" to SyncManager.newId("ord"),
                    "items" to g.cart.map { mapOf("variant_id" to it.variant.str("variant_id"), "quantity" to it.quantity) },
                    "discount_code" to code.ifBlank { null },
                    "payment" to mapOf("token" to token),
                )
                val r = g.api.post("/api/v1/checkout", body)
                val id = r.str("order_id") ?: ""
                receipts[id] = r
                g.cart.clear()
                ui.toast("Payment successful. Your receipt is ready.")
                ui.nav.navigate("receipt/$id") { popUpTo("store") }
            } catch (e: ApiError) {
                error = if (e.isNetwork) "Payment needs a connection. Nothing was charged." else e.message
            } finally { busy = false }
        }
    }
}

@Composable
fun ReceiptScreen(orderId: String) {
    val g = graph()
    val ui = LocalUi.current
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val orders = rememberRes(if (receipts[orderId] == null) "/api/v1/orders" else null)
    val products = rememberRes("/api/v1/products")
    val r = receipts[orderId] ?: orders.loaded?.data?.arr("orders")?.firstOrNull { it.str("order_id") == orderId }
    var busy by remember { mutableStateOf(false) }
    val names = products.loaded?.data?.arr("products")?.flatMap { p -> p.arr("variants").map { (it.str("variant_id") ?: "") to ((p.str("name") ?: "") + " · " + attrShort(it)) } }?.toMap() ?: emptyMap()

    fun withPdf(after: (File) -> Unit) {
        busy = true
        scope.launch {
            try {
                val bytes = g.api.bytes("/api/v1/orders/$orderId/receipt.pdf")
                val f = withContext(Dispatchers.IO) {
                    File(ctx.cacheDir, "receipts").apply { mkdirs() }.let { File(it, "receipt-$orderId.pdf") }.also { it.writeBytes(bytes) }
                }
                after(f)
            } catch (e: ApiError) {
                ui.toast(if (e.isNetwork) "Downloading the receipt needs a connection." else e.message)
            } catch (e: Exception) {
                ui.toast("Couldn't open the receipt on this phone.")
            } finally { busy = false }
        }
    }

    Page("Receipt", back = true) {
        if (r == null) { if (orders.error != null) ErrorState(orders.error, orders.reload) else Loading(); return@Page }
        val currency = r.str("currency") ?: "PKR"
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
            Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface).padding(20.dp), horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Icon(Icons.Filled.CheckCircle, null, tint = extra.ok, modifier = Modifier.size(40.dp))
                Text("Paid", style = MaterialTheme.typography.titleLarge)
                Text(money(r.long("total_minor"), currency), style = ScoreStyle.copy(fontSize = 32.sp))
                Text("Order $orderId", fontSize = 12.sp, color = extra.muted)
                (r.obj("receipt")?.obj("payload")?.str("paid_at") ?: r.str("paid_at"))?.let { Text("Paid at ${it.replace("T", " ").removeSuffix("Z")} UTC", fontSize = 12.sp, color = extra.muted) }
            }
            SectionLabel("Items")
            r.arr("items").forEach { it ->
                RowItem {
                    Row {
                        Text("${it.int("quantity")} × ${names[it.str("variant_id")] ?: it.str("variant_id")}", Modifier.weight(1f))
                        Text(money((it.long("unit_price_minor") ?: 0) * (it.int("quantity") ?: 1), currency), style = NumStyle)
                    }
                }
                Divider()
            }
            r.long("discount_minor")?.takeIf { it > 0 }?.let { RowItem { Row { Text("Discount", Modifier.weight(1f), color = extra.muted); Text("−" + money(it, currency), style = NumStyle) } } }
            RowItem { Row { Text("Total", Modifier.weight(1f), fontWeight = FontWeight.Bold); Text(money(r.long("total_minor"), currency), style = NumStyle, fontWeight = FontWeight.Bold) } }
            SectionLabel("Receipt PDF")
            Column(Modifier.padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { withPdf { open(ctx, it) } }, enabled = !busy, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) {
                    Icon(Icons.Filled.OpenInNew, null); Text("  View PDF")
                }
                OutlinedButton(onClick = { withPdf { saved -> ui.toast(if (saveToDownloads(ctx, saved)) "Saved to Downloads." else "Couldn't save; use Share instead.") } },
                    enabled = !busy, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) { Icon(Icons.Filled.Download, null); Text("  Download") }
                OutlinedButton(onClick = { withPdf { share(ctx, it) } }, enabled = !busy, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) {
                    Icon(Icons.Filled.Share, null); Text("  Share")
                }
            }
            Box(Modifier.height(24.dp))
        }
    }
}

private fun uri(ctx: Context, f: File) = FileProvider.getUriForFile(ctx, ctx.packageName + ".files", f)

private fun open(ctx: Context, f: File) {
    val i = Intent(Intent.ACTION_VIEW).setDataAndType(uri(ctx, f), "application/pdf").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    try { ctx.startActivity(Intent.createChooser(i, "Open receipt")) } catch (e: Exception) { share(ctx, f) }
}

private fun share(ctx: Context, f: File) {
    val i = Intent(Intent.ACTION_SEND).setType("application/pdf").putExtra(Intent.EXTRA_STREAM, uri(ctx, f)).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    ctx.startActivity(Intent.createChooser(i, "Share receipt"))
}

private fun saveToDownloads(ctx: Context, f: File): Boolean = try {
    if (Build.VERSION.SDK_INT >= 29) {
        val values = ContentValues().apply {
            put(MediaStore.Downloads.DISPLAY_NAME, f.name)
            put(MediaStore.Downloads.MIME_TYPE, "application/pdf")
        }
        val u = ctx.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)!!
        ctx.contentResolver.openOutputStream(u)!!.use { it.write(f.readBytes()) }
        true
    } else false
} catch (e: Exception) { false }

@Composable
fun OrdersScreen() {
    val ui = LocalUi.current
    val res = rememberRes("/api/v1/orders")
    Page("Orders", back = true, savedAt = res.loaded?.savedAt) {
        ResBox(res) { l ->
            val orders = l.data.arr("orders")
            if (orders.isEmpty()) {
                Empty(Icons.AutoMirrored.Filled.ReceiptLong, "No orders yet", "Your receipts appear here after you buy something."); return@ResBox
            }
            LazyColumn(Modifier.fillMaxSize()) {
                items(orders, key = { it.str("order_id") ?: "" }) { o ->
                    RowItem(onClick = { ui.nav.navigate("receipt/${o.str("order_id")}") }) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(money(o.long("total_minor")), style = NumStyle, fontWeight = FontWeight.Medium)
                                Text("${Messages.label(o.str("status"))} · ${o.str("paid_at")?.take(10) ?: ""}", fontSize = 12.sp, color = extra.muted)
                            }
                            Text("View", color = extra.link)
                        }
                    }
                    Divider()
                }
            }
        }
    }
}
