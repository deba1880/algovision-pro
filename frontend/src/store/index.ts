import { configureStore } from '@reduxjs/toolkit'
import marketReducer from './slices/marketSlice'
import chartReducer from './slices/chartSlice'
import tradingReducer from './slices/tradingSlice'
import signalReducer from './slices/signalSlice'
import robotReducer from './slices/robotSlice'

export const store = configureStore({
  reducer: {
    market: marketReducer,
    chart: chartReducer,
    trading: tradingReducer,
    signals: signalReducer,
    robot: robotReducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware({ serializableCheck: false }),
})

export type RootState = ReturnType<typeof store.getState>
export type AppDispatch = typeof store.dispatch
