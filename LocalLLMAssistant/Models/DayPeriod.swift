import Foundation

enum DayPeriod: CaseIterable, Sendable {
    case earlyMorning
    case morning
    case midday
    case afternoon
    case evening
    case lateNight

    static func current(for date: Date = Date(), calendar: Calendar = .current) -> DayPeriod {
        let hour = calendar.component(.hour, from: date)
        switch hour {
        case 5..<9:
            return .earlyMorning
        case 9..<12:
            return .morning
        case 12..<14:
            return .midday
        case 14..<18:
            return .afternoon
        case 18..<22:
            return .evening
        default:
            return .lateNight
        }
    }
}
