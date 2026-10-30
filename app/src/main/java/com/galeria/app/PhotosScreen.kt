package com.galeria.app

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayCircle
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun PhotosScreen() {
    val context = LocalContext.current
    val photos by produceState(emptyList<Photo>()) {
        value = withContext(Dispatchers.IO) { loadPhotos(context) }
    }
    var openIndex by remember { mutableStateOf<Int?>(null) }
    val monthFmt = remember { SimpleDateFormat("MMMM 'de' yyyy", Locale("pt", "BR")) }
    val groups = remember(photos) { photos.withIndex().groupBy { monthFmt.format(Date(it.value.dateTaken)) } }

    LazyVerticalGrid(columns = GridCells.Fixed(4), modifier = Modifier.fillMaxSize()) {
        groups.forEach { (month, items) ->
            item(span = { GridItemSpan(maxLineSpan) }) {
                Text(
                    month.replaceFirstChar { it.uppercase() },
                    fontWeight = FontWeight.Bold, fontSize = 18.sp,
                    modifier = Modifier.padding(12.dp),
                )
            }
            items(items, key = { it.value.id }) { (index, photo) ->
                Box(Modifier.aspectRatio(1f).padding(1.dp).clickable { openIndex = index }) {
                    AsyncImage(photo.uri, null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
                    if (photo.isVideo) Icon(
                        Icons.Filled.PlayCircle, null, tint = Color.White,
                        modifier = Modifier.align(Alignment.TopEnd).padding(4.dp),
                    )
                }
            }
        }
    }

    openIndex?.let { start ->
        BackHandler { openIndex = null }
        val pager = rememberPagerState(start) { photos.size }
        HorizontalPager(pager, Modifier.fillMaxSize().background(Color.Black)) { page ->
            ZoomableImage(photos[page])
        }
    }
}

@Composable
private fun ZoomableImage(photo: Photo) {
    var scale by remember { mutableFloatStateOf(1f) }
    Box(
        Modifier.fillMaxSize().pointerInput(Unit) {
            detectTransformGestures { _, _, zoom, _ -> scale = (scale * zoom).coerceIn(1f, 5f) }
        },
    ) {
        AsyncImage(
            photo.uri, null, contentScale = ContentScale.Fit,
            modifier = Modifier.fillMaxSize().graphicsLayer(scaleX = scale, scaleY = scale),
        )
        if (photo.isVideo) Text(
            "Vídeo", color = MaterialTheme.colorScheme.primary,
            modifier = Modifier.align(Alignment.BottomCenter).padding(24.dp),
        )
    }
}
