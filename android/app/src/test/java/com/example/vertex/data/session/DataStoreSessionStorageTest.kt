package com.example.vertex.data.session

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import com.example.vertex.testutil.FakeTokenCipher
import com.example.vertex.testutil.TEST_SESSION
import java.io.File
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class DataStoreSessionStorageTest {
    @get:Rule val tmp = TemporaryFolder()

    private fun TestScope.dataStore(): DataStore<Preferences> =
        PreferenceDataStoreFactory.create(scope = backgroundScope) { File(tmp.root, "session.preferences_pb") }

    @Test fun `no session by default`() = runTest {
        assertNull(DataStoreSessionStorage(dataStore(), FakeTokenCipher()).session.first())
    }

    @Test fun `save then read returns the same session`() = runTest {
        val storage = DataStoreSessionStorage(dataStore(), FakeTokenCipher())
        storage.save(TEST_SESSION)
        assertEquals(TEST_SESSION, storage.session.first())
    }

    @Test fun `tokens are stored encrypted, not in plain text`() = runTest {
        val ds = dataStore()
        DataStoreSessionStorage(ds, FakeTokenCipher()).save(TEST_SESSION)
        val raw = ds.data.first()
        val storedAccess = raw[DataStoreSessionStorage.ACCESS]!!
        val storedRefresh = raw[DataStoreSessionStorage.REFRESH]!!
        assertFalse(storedAccess.contains(TEST_SESSION.accessToken))
        assertFalse(storedRefresh.contains(TEST_SESSION.refreshToken))
    }

    @Test fun `clear removes the session`() = runTest {
        val storage = DataStoreSessionStorage(dataStore(), FakeTokenCipher())
        storage.save(TEST_SESSION)
        storage.clear()
        assertNull(storage.session.first())
    }

    @Test fun `undecryptable tokens are treated as no session`() = runTest {
        val ds = dataStore()
        DataStoreSessionStorage(ds, FakeTokenCipher()).save(TEST_SESSION)
        val broken = object : com.example.vertex.core.security.TokenCipher {
            override fun encrypt(plain: String) = plain
            override fun decrypt(encoded: String): String = error("key lost")
        }
        assertNull(DataStoreSessionStorage(ds, broken).session.first())
    }
}
