from lib.window_arena import *
from lib.winobj_ship import *
from typing import List

# update ship (this is where your code goes)
# Karim M's bot. Every time the game asks for new commands:
#   1. If I have ammo and a quick shot, shoot it (aiming where the target is going).
#   2. Otherwise fly to the best powerup (ammo first if I'm out).
#   3. If no powerup is worth it, fly to where the nearest target is heading.
# Every command costs points (-1 for a move or turn, -2 for a shot), so the bot
# only does one useful thing at a time.
def updateShipMohamed(ship: Ship, powerUps: List[PowerUp], targets: List[Target]):
    ship.setPlayerName("Karim M")

    # Settings (picked by testing lots of practice matches)
    BULLET_SPEED = 8          # how fast bullets fly (units per second)
    ENEMY_SHOT_RANGE = 4      # only shoot the enemy ship when it's this close
    AMMO_BONUS = 2            # how many seconds I'll "go out of my way" for ammo when I'm empty
    PACK_BONUS = 0.3          # extra seconds per ammo in the pack (a 3-pack beats a 1-pack)
    LATE_BOOST_PENALTY = 3    # boosts barely help in the last 30 seconds
    POWERUP_LIMIT = 3         # with ammo, skip powerups more than this many seconds away
    MAX_MOVE = 8              # longest single move, so I can rethink on the way

    timeLeft = ship.window.levelTime
    enemy = ship.getOther()          # None if there's no other ship
    maxX = ship.window.maxCoordinateX()
    maxY = ship.window.maxCoordinateY()

    # Distance from point a to point b
    def distance(a, b):
        return length(b - a)

    # Degrees to turn from one direction to another, between -180 and 180.
    # Positive = counterclockwise, negative = clockwise.
    def turnNeeded(facing, direction):
        angle = angleDeg(direction) - angleDeg(facing)
        while angle > 180:
            angle = angle - 360
        while angle < -180:
            angle = angle + 360
        return angle

    # Seconds for a ship to turn toward a spot, and to turn + fly there
    def turnTime(someShip, spot):
        return abs(turnNeeded(someShip.dir, spot - someShip.pos)) / someShip.shipTurnSpeed

    def travelTime(someShip, spot):
        return turnTime(someShip, spot) + distance(someShip.pos, spot) / someShip.shipMoveSpeed

    # True if a spot is inside the arena (not too close to the edge)
    def onScreen(spot):
        return spot[0] > 0.6 and spot[0] < maxX - 0.6 and spot[1] > 0.6 and spot[1] < maxY - 0.6

    # Fly toward a spot: turn to face it, then thrust (at most MAX_MOVE units).
    def flyTo(spot):
        direction = spot - ship.pos
        angle = turnNeeded(ship.dir, direction)
        if angle > 1:
            ship.queueCommand(ShipCmd_ThrustRight(angle))     # right thrusters turn counterclockwise
        elif angle < -1:
            ship.queueCommand(ShipCmd_ThrustLeft(-angle))     # left thrusters turn clockwise
        moveBy = min(length(direction), MAX_MOVE)
        if moveBy > 0.3:
            ship.queueCommand(ShipCmd_Thrust(moveBy))

    # ---------- 1. Shoot ----------
    if ship.ammo > 0:
        bestAim = None
        bestTime = 1000

        for target in targets:
            if target.isDying():
                continue
            # Guess where the target will be, then improve the guess once using the better spot.
            # time = time to turn toward it + time for the bullet to fly there
            aim = target.pos
            time = 0
            for i in range(2):
                time = turnTime(ship, aim) + max(distance(ship.pos, aim) - 0.5, 0) / BULLET_SPEED
                aim = target.pos + target.vel * time
            d = distance(ship.pos, aim)
            if d > 0.8 and d < ship.ammoMaxRange - 0.5 and onScreen(aim) and time < timeLeft - 0.2:
                if time < bestTime:                    # the quickest shot is the surest shot
                    bestTime = time
                    bestAim = aim

        # The enemy ship is worth more (+25 vs +20), but it's small and it moves on its own,
        # so I only shoot it when it's close and not moving, and quicker to hit than a target.
        if enemy is not None and length(enemy.vel) < 0.1:
            d = distance(ship.pos, enemy.pos)
            time = turnTime(ship, enemy.pos) + d / BULLET_SPEED
            if d > 0.8 and d < ENEMY_SHOT_RANGE and time < timeLeft - 0.2 and time < bestTime:
                bestAim = enemy.pos

        if bestAim is not None:
            ship.queueCommand(ShipCmd_Shoot(bestAim - ship.pos))
            return

    # Near the end, moving can't earn points anymore, so don't spend any
    if timeLeft < 1.5:
        return

    # ---------- 2. Pick the best powerup ----------
    # Score = seconds to get there, adjusted for how useful it is. Lower is better.
    bestPowerUp = None
    bestScore = 1000
    for powerUp in powerUps:
        if powerUp.isDying():
            continue
        myTime = travelTime(ship, powerUp.pos)

        # Skip powerups the enemy will clearly reach first
        if enemy is not None and travelTime(enemy, powerUp.pos) < myTime * 0.7:
            continue

        score = myTime
        if powerUp.type == "1" or powerUp.type == "2" or powerUp.type == "3":
            if ship.ammo == 0:
                score = score - AMMO_BONUS
            score = score - int(powerUp.type) * PACK_BONUS
        elif powerUp.type == "R" or powerUp.type == "S":
            if timeLeft < 30:
                score = score + LATE_BOOST_PENALTY

        if score < bestScore:
            bestScore = score
            bestPowerUp = powerUp

    if bestPowerUp is not None and (ship.ammo == 0 or bestScore < POWERUP_LIMIT):
        flyTo(bestPowerUp.pos)
        return

    # ---------- 3. Get in range of the nearest target ----------
    if ship.ammo > 0:
        closest = None
        closestTime = 1000
        for target in targets:
            if target.isDying():
                continue
            t = travelTime(ship, target.pos)
            if t < closestTime:
                closestTime = t
                closest = target

        if closest is not None:
            # Head for where the target will be by the time I get there
            future = closest.pos + closest.vel * closestTime
            toTarget = future - ship.pos
            moveBy = length(toTarget) - ship.ammoMaxRange * 0.5
            if moveBy > 0.5:
                flyTo(ship.pos + unit(toTarget) * moveBy)
                return

    # Nothing else to do: go get the best powerup anyway
    if bestPowerUp is not None:
        flyTo(bestPowerUp.pos)



####################################################################################################
############################## DO NOT MODIFY  METHODS BELOW THIS LINE ##############################
########################## EXCEPT TO REMOVE TUTORIAL GAME CONFIG ARGUMENT  #########################
####################################################################################################
WindowArena(userCode1 = updateShipMohamed,
            gameConfig = WindowArenaConfig.SPACE_BATTLE,
            windowTitle = "TSA@RHS: Space Battle!").runGameLoop()