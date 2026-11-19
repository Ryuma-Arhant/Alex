import { configureStore } from '@reduxjs/toolkit'
import { api } from '../api/api'
import bulk from '../features/bulk/slice'
import call from '../features/call/slice'
import transcript from '../features/transcript/slice'
export const makeStore = () =>
  configureStore({
    reducer: { [api.reducerPath]: api.reducer, call, transcript, bulk },
    middleware: (gdm) => gdm().concat(api.middleware),
  })
export const store = makeStore()
