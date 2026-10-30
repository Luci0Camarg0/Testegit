package com.galeria.app

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

data class Playlist(val id: Long, val name: String, val songIds: List<Long>)

data class Note(val id: Long, val title: String, val body: String, val pinned: Boolean, val updatedAt: Long)

/** Guarda playlists e notas no próprio celular, em JSON. */
class Store(context: Context) {
    private val prefs = context.getSharedPreferences("galeria_store", Context.MODE_PRIVATE)

    fun loadPlaylists(): List<Playlist> {
        val arr = JSONArray(prefs.getString("playlists", "[]"))
        return (0 until arr.length()).map { i ->
            val o = arr.getJSONObject(i)
            val ids = o.getJSONArray("songs")
            Playlist(o.getLong("id"), o.getString("name"), (0 until ids.length()).map { ids.getLong(it) })
        }
    }

    fun savePlaylists(list: List<Playlist>) {
        val arr = JSONArray()
        list.forEach { p ->
            arr.put(JSONObject().put("id", p.id).put("name", p.name).put("songs", JSONArray(p.songIds)))
        }
        prefs.edit().putString("playlists", arr.toString()).apply()
    }

    fun loadNotes(): List<Note> {
        val arr = JSONArray(prefs.getString("notes", "[]"))
        return (0 until arr.length()).map { i ->
            val o = arr.getJSONObject(i)
            Note(o.getLong("id"), o.getString("title"), o.getString("body"), o.getBoolean("pinned"), o.getLong("updatedAt"))
        }
    }

    fun saveNotes(list: List<Note>) {
        val arr = JSONArray()
        list.forEach { n ->
            arr.put(
                JSONObject().put("id", n.id).put("title", n.title).put("body", n.body)
                    .put("pinned", n.pinned).put("updatedAt", n.updatedAt),
            )
        }
        prefs.edit().putString("notes", arr.toString()).apply()
    }
}
