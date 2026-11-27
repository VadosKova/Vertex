package com.example.vertex.domain.repository

import com.example.vertex.domain.model.Session
import kotlinx.coroutines.flow.Flow

interface SessionStorage {
    val session: Flow<Session?>
    suspend fun save(session: Session)
    suspend fun clear()
}
