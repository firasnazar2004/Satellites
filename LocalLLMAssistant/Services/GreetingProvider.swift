import Foundation

struct GreetingProvider: Sendable {
    private(set) var previousGreeting: String?

    mutating func greeting(for date: Date = Date(), calendar: Calendar = .current) -> String {
        let period = DayPeriod.current(for: date, calendar: calendar)
        return greeting(for: period)
    }

    mutating func greeting(for period: DayPeriod) -> String {
        let candidates = Self.greetings(for: period)
        guard !candidates.isEmpty else {
            let fallback = "What are we working through?"
            previousGreeting = fallback
            return fallback
        }

        let availableCandidates = candidates.filter { $0 != previousGreeting }
        let selected = (availableCandidates.isEmpty ? candidates : availableCandidates).randomElement() ?? candidates[0]
        previousGreeting = selected
        return selected
    }

    static func greetings(for period: DayPeriod) -> [String] {
        switch period {
        case .earlyMorning:
            return [
                "Up early, Massa?",
                "Early start. What's first?",
                "Morning, Massa. Already at it?",
                "Starting early today?",
                "Early session, Massa?",
                "What are we getting into this early?",
                "Sun's barely up. What's the plan?",
                "An early one today, Massa?",
                "Starting the day ahead of schedule?",
                "What are we tackling first?"
            ]
        case .morning:
            return [
                "Morning, Massa. What's first?",
                "Good morning. What's on the agenda?",
                "Fresh start, Massa. Where do we begin?",
                "Morning. What's the plan?",
                "What are we working through today?",
                "New day, new question?",
                "Morning, Massa. Where do we start?",
                "What's the mission this morning?",
                "What needs your attention first?",
                "Ready for the day, Massa?"
            ]
        case .midday:
            return [
                "Midday check-in, Massa. What's next?",
                "What are we working through, Massa?",
                "Halfway through the day. What's next?",
                "What's on the agenda?",
                "Midday mission?",
                "What are we tackling next?",
                "Still got momentum, Massa?",
                "What's the next thing?",
                "What's left for the afternoon?",
                "Where are we picking up?"
            ]
        case .afternoon:
            return [
                "Afternoon, Massa. What are we tackling?",
                "What's the afternoon mission?",
                "Still going?",
                "What are we working through next, Massa?",
                "Afternoon. What needs attention?",
                "What's on your plate, Massa?",
                "Keeping the momentum?",
                "What's left on the list?",
                "Afternoon, Massa. What's next?",
                "One thing at a time. What's first?"
            ]
        case .evening:
            return [
                "Evening, Massa. What's on your mind?",
                "Evening session?",
                "What's the evening mission, Massa?",
                "Still at it?",
                "What are we working through tonight?",
                "Evening, Massa. What's on the agenda?",
                "One more thing to get through?",
                "What are we getting done tonight?",
                "Evening, Massa. Where do we start?",
                "What's left for tonight?"
            ]
        case .lateNight:
            return [
                "Some late-night work, Massa?",
                "Late-night study session?",
                "Burning the midnight oil, Massa?",
                "Still working through it?",
                "One more thing before bed?",
                "Night session, Massa?",
                "Couldn't leave it for tomorrow?",
                "Still studying?",
                "One last thing?",
                "What are we getting through tonight, Massa?",
                "Still at it this late?",
                "Finishing something up, Massa?",
                "Late-night research?",
                "One more page?",
                "Can't call it a night just yet?"
            ]
        }
    }
}
